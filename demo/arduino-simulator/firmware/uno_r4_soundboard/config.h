#pragma once

// 비워 두면 UNO-R4-Sound에 직접 연결합니다. API 토큰은 사용하지 않습니다.
// 공유기를 사용하려면 2.4GHz Wi-Fi 이름/비밀번호를 입력하고 다시 업로드하세요.
constexpr char WIFI_SSID[] = "";
constexpr char WIFI_PASSWORD[] = "";
constexpr char AP_SSID[] = "UNO-R4-Sound";
// 기본 AP는 비밀번호가 없습니다. 원하면 8자 이상 Wi-Fi 비밀번호를 설정하세요.
constexpr char AP_PASSWORD[] = "";

// 기본: SSD1306 128x64, A4/A5의 Wire, I2C 0x3C/0x3D 자동 탐색.
// 3.3V Qwiic으로 실제 배선을 옮긴 경우에만 true로 바꾸세요.
constexpr bool OLED_USE_QWIIC = false;
constexpr bool ENABLE_STATUS_LEDS = true;
constexpr unsigned char LED_BRIGHTNESS = 20;  // 0~255, 낮은 밝기로 시작
