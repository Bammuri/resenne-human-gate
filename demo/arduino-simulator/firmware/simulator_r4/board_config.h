#pragma once
// Simulator-compatible controller: no board API token.
#include "wifi_credentials.h"
// SSD1306 128x64: default Wire on A4/A5. Only select Wire1 after Qwiic rewiring.
constexpr bool OLED_USE_QWIIC = false;
// A0 is a context control (AI level / navigation), not a dedicated volume knob.
// Current wiring: clockwise rotation increases the reported AI level.
constexpr bool POT_REVERSED = true;
