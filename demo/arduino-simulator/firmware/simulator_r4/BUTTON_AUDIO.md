# Button audio

Files must be in the DFPlayer Pro internal storage root. Playback uses exact
paths (`AT+PLAYFILE=/soundN.mp3`), not storage enumeration order.

| Profile | Buttons | Files |
| --- | --- | --- |
| Agent (mode 1) | 1–7 | sound1.mp3–sound7.mp3 |
| Workflow (mode 2) | 1–7 | sound9.mp3–sound15.mp3 |
| Custom (mode 3) | 1–4 | sound16.mp3–sound19.mp3 |
| Custom (mode 3) | 5–6 | No assigned sound |
| Custom (mode 3) | 7 | STOP: cancel pending playback, amplifier off |
| All profiles | 8 (MODE) | sound8.mp3 |

The website synchronizes the active profile through `display:` commands.
Physical presses and simulated `key:` commands both trigger audio on the board;
the website must not play a second copy on receiving the key event.
Assignments remain slot-based even when the website displays answer choices.

Playback is single-track, non-looping. Rapid presses replace pending audio with
the latest assigned sound, without delaying key events. Existing manual audio
controls remain available. Custom keys 1–4 are 거제야호, 오이시, 러브어택, 대자부;
key 7 is speaker STOP (not AI stop or volume selection). These keys stay reserved
even during AI questions. They require a connected real board, and screen clicks
use the existing board round-trip without duplicate audio commands. MODE only
switches profiles. In Custom mode the knob always controls volume (0–30,
clockwise increases); no key selection is required. Pressing another key does
not exit volume control, and key 7 still stops audio. Switching out of Custom
restores the mode's AI knob function. Entry does not change the current volume.
Physical A0 applies locally; screen knob left/right commands adjust by one and
must not be sent a second time by the website. Volume also remains adjustable
in the hardware audio settings.
Refresh the website after updating. Existing custom settings are preserved but
overridden for these reserved slots.
Compilation and mapping checks do not verify the presence or audible content
of files on the DFPlayer.

## Working-reference playback

All audio commands share one queue, paced at 250 ms, matching the actual working
source supplied by the user. Missing `OK` does not cancel playback. CR, LF and
CRLF responses are logged, without assuming they acknowledge the latest command.
`AUDIO_SENT` only means UART transmission. Explicit ERR responses clear pending
commands. `/status` includes `audioReply` and `audioError` for diagnosis.

Startup: wait 2 s, VOL=0, wait 250 ms, FUNCTION=1, wait 2 s, AMP=OFF,
wait 250 ms, PLAYMODE=3, wait 250 ms, VOL=3. Button playback: desired volume,
AMP=ON, 500 ms amplifier warm-up, exact file path. This avoids starting the
file while the amplifier is muted. Other command gaps remain 250 ms.
STOP cancels queued file starts and sends AMP=OFF immediately. There is no TIME command. The initial
volume is deliberately quiet (3/30); subsequent volume controls allow 0–30.
Reboot persistence is not implemented. USB `audio:test` plays `/sound1.mp3` at
3/30 without dispatching any AI key action; `audio:stop` cancels pending playback
and mutes the amplifier.

## Simple SSD1306 display

The 128x64 OLED uses only the built-in 6x8 font at size 1, with four rows
at y=4,18,32,46, x=4, and at most 20 printable ASCII characters per row. No large
text, shapes, timer or animation is drawn. Changed frames clear the entire
framebuffer and transfer once; identical frames are skipped. The bounded
`oled_text_frame.h` helper must stay beside the sketch when copying it.
