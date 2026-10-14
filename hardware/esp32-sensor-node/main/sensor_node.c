/*
 * InkyPi sensor node for the ESP32-S3.
 *
 * Publishes to the MQTT Dashboard plugin with no extra hardware:
 *   inkypi/<node>/state   {"temp_c":..,"rssi":..,"heap_kb":..,"uptime_s":..} every interval (retained)
 *   inkypi/<node>/button  "pressed" / "released" when the BOOT button changes (retained)
 *   inkypi/<node>/status  "online", or "offline" via last will when the node drops off (retained)
 *
 * Configure Wi-Fi and the broker with `idf.py menuconfig` -> InkyPi Sensor Node.
 */

#include <stdio.h>
#include <stdbool.h>

#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"
#include "freertos/task.h"

#include "driver/gpio.h"
#include "driver/temperature_sensor.h"
#include "esp_event.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "esp_wifi.h"
#include "mqtt_client.h"
#include "nvs_flash.h"

#define TOPIC_ROOT "inkypi/" CONFIG_NODE_NAME
#define TOPIC_STATE TOPIC_ROOT "/state"
#define TOPIC_BUTTON TOPIC_ROOT "/button"
#define TOPIC_STATUS TOPIC_ROOT "/status"

#define WIFI_CONNECTED_BIT BIT0
#define MQTT_CONNECTED_BIT BIT1

#define BUTTON_POLL_MS 20
#define BUTTON_STABLE_SAMPLES 3

static const char *TAG = "sensor_node";

static EventGroupHandle_t s_events;
static esp_mqtt_client_handle_t s_mqtt;
static temperature_sensor_handle_t s_tsens;
static volatile bool s_button_pressed;

static void wifi_event_handler(void *arg, esp_event_base_t base, int32_t id, void *data)
{
    if (base == WIFI_EVENT && id == WIFI_EVENT_STA_START) {
        esp_wifi_connect();
    } else if (base == WIFI_EVENT && id == WIFI_EVENT_STA_DISCONNECTED) {
        xEventGroupClearBits(s_events, WIFI_CONNECTED_BIT);
        ESP_LOGW(TAG, "Wi-Fi disconnected, retrying");
        vTaskDelay(pdMS_TO_TICKS(1000));
        esp_wifi_connect();
    } else if (base == IP_EVENT && id == IP_EVENT_STA_GOT_IP) {
        ip_event_got_ip_t *event = (ip_event_got_ip_t *)data;
        ESP_LOGI(TAG, "Got IP " IPSTR, IP2STR(&event->ip_info.ip));
        xEventGroupSetBits(s_events, WIFI_CONNECTED_BIT);
    }
}

static void wifi_start(void)
{
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    esp_netif_create_default_wifi_sta();

    wifi_init_config_t init_cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&init_cfg));
    ESP_ERROR_CHECK(esp_event_handler_register(WIFI_EVENT, ESP_EVENT_ANY_ID, wifi_event_handler, NULL));
    ESP_ERROR_CHECK(esp_event_handler_register(IP_EVENT, IP_EVENT_STA_GOT_IP, wifi_event_handler, NULL));

    wifi_config_t wifi_cfg = {
        .sta = {
            .ssid = CONFIG_NODE_WIFI_SSID,
            .password = CONFIG_NODE_WIFI_PASSWORD,
        },
    };
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &wifi_cfg));
    ESP_ERROR_CHECK(esp_wifi_start());
}

static void publish_button(void)
{
    esp_mqtt_client_publish(s_mqtt, TOPIC_BUTTON, s_button_pressed ? "pressed" : "released", 0, 1, 1);
}

static void mqtt_event_handler(void *arg, esp_event_base_t base, int32_t id, void *data)
{
    switch ((esp_mqtt_event_id_t)id) {
    case MQTT_EVENT_CONNECTED:
        ESP_LOGI(TAG, "MQTT connected");
        xEventGroupSetBits(s_events, MQTT_CONNECTED_BIT);
        esp_mqtt_client_publish(s_mqtt, TOPIC_STATUS, "online", 0, 1, 1);
        publish_button();
        break;
    case MQTT_EVENT_DISCONNECTED:
        ESP_LOGW(TAG, "MQTT disconnected");
        xEventGroupClearBits(s_events, MQTT_CONNECTED_BIT);
        break;
    case MQTT_EVENT_ERROR:
        ESP_LOGE(TAG, "MQTT error");
        break;
    default:
        break;
    }
}

static void mqtt_start(void)
{
    esp_mqtt_client_config_t cfg = {
        .broker.address.uri = CONFIG_NODE_MQTT_BROKER_URI,
        .credentials = {
            .client_id = CONFIG_NODE_NAME,
            .username = CONFIG_NODE_MQTT_USERNAME[0] ? CONFIG_NODE_MQTT_USERNAME : NULL,
            .authentication.password = CONFIG_NODE_MQTT_PASSWORD[0] ? CONFIG_NODE_MQTT_PASSWORD : NULL,
        },
        .session.last_will = {
            .topic = TOPIC_STATUS,
            .msg = "offline",
            .qos = 1,
            .retain = 1,
        },
    };
    s_mqtt = esp_mqtt_client_init(&cfg);
    ESP_ERROR_CHECK(esp_mqtt_client_register_event(s_mqtt, ESP_EVENT_ANY_ID, mqtt_event_handler, NULL));
    ESP_ERROR_CHECK(esp_mqtt_client_start(s_mqtt));
}

static void publish_task(void *arg)
{
    char payload[160];
    while (true) {
        xEventGroupWaitBits(s_events, MQTT_CONNECTED_BIT, pdFALSE, pdTRUE, portMAX_DELAY);

        float temp_c = 0;
        temperature_sensor_get_celsius(s_tsens, &temp_c);

        wifi_ap_record_t ap = {0};
        int rssi = esp_wifi_sta_get_ap_info(&ap) == ESP_OK ? ap.rssi : 0;

        snprintf(payload, sizeof(payload),
                 "{\"temp_c\":%.1f,\"rssi\":%d,\"heap_kb\":%lu,\"uptime_s\":%lld}",
                 temp_c, rssi,
                 (unsigned long)(esp_get_free_heap_size() / 1024),
                 (long long)(esp_timer_get_time() / 1000000));
        // Retained so the dashboard has a value right after InkyPi restarts.
        esp_mqtt_client_publish(s_mqtt, TOPIC_STATE, payload, 0, 0, 1);
        ESP_LOGI(TAG, "%s %s", TOPIC_STATE, payload);

        vTaskDelay(pdMS_TO_TICKS(CONFIG_NODE_PUBLISH_INTERVAL_S * 1000));
    }
}

static void button_task(void *arg)
{
    gpio_config_t io = {
        .pin_bit_mask = 1ULL << CONFIG_NODE_BUTTON_GPIO,
        .mode = GPIO_MODE_INPUT,
        .pull_up_en = GPIO_PULLUP_ENABLE,
    };
    ESP_ERROR_CHECK(gpio_config(&io));

    bool last_raw = gpio_get_level(CONFIG_NODE_BUTTON_GPIO) == 0;
    int stable = 0;
    s_button_pressed = last_raw;

    while (true) {
        bool raw = gpio_get_level(CONFIG_NODE_BUTTON_GPIO) == 0;  // active low
        stable = (raw == last_raw) ? stable + 1 : 0;
        last_raw = raw;

        if (stable == BUTTON_STABLE_SAMPLES && raw != s_button_pressed) {
            s_button_pressed = raw;
            ESP_LOGI(TAG, "Button %s", raw ? "pressed" : "released");
            if (xEventGroupGetBits(s_events) & MQTT_CONNECTED_BIT) {
                publish_button();
            }
        }
        vTaskDelay(pdMS_TO_TICKS(BUTTON_POLL_MS));
    }
}

void app_main(void)
{
    esp_err_t err = nvs_flash_init();
    if (err == ESP_ERR_NVS_NO_FREE_PAGES || err == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        err = nvs_flash_init();
    }
    ESP_ERROR_CHECK(err);

    s_events = xEventGroupCreate();

    temperature_sensor_config_t tsens_cfg = TEMPERATURE_SENSOR_CONFIG_DEFAULT(-10, 80);
    ESP_ERROR_CHECK(temperature_sensor_install(&tsens_cfg, &s_tsens));
    ESP_ERROR_CHECK(temperature_sensor_enable(s_tsens));

    wifi_start();
    xEventGroupWaitBits(s_events, WIFI_CONNECTED_BIT, pdFALSE, pdTRUE, portMAX_DELAY);
    mqtt_start();

    xTaskCreate(publish_task, "publish", 4096, NULL, 5, NULL);
    xTaskCreate(button_task, "button", 2048, NULL, 5, NULL);
}
