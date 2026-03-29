# demo.py - demonstrates the capabilities of audio_dsl in increasing complexity
#
# author      : Werner Thie, wth
#		        ChatGPT, cpt as code companion
# last edit   : 27.02.2026
# mod_history :
#   04.03.2026 - cpt, wth created after a crazy long session with ChatGPT

"""
    How the demo progresses

    Step 1 — Basic envelope pulse: attack, sustain, release.

    Step 2 — Continuous SINE wobble on volume, subtle modulation.

    Step 3 — TRIANGLE wobble of _attack envelope synced to envelope cycles.

    Step 4 — Procedural sequence with trigger-based activation, using a continuous volume wobble.

    Step 5 — Live REPL coding, shows you can execute code on-the-fly (set_freq, wobble).

    Step 6 — Imported sequence from standard Python list; runs multiple cycles programmatically.

    Final fade-out — Demonstrates negative-depth wobble to smoothly bring volume down.
"""

import time

from audio_engine import (
    start, stop,
    set_env, set_freq, set_vol,
    wobble
)

from audio_dsl import (
    run_sequence_forever, stop_sequence,
    set_trigger, toggle_trigger, repl_exec
)


# ==============================
# Step 0: Start audio thread
# ==============================
start()
set_vol(0.3)
set_freq(440)   # A4 baseline


# # ==============================
# # Step 1: Simple envelope pulse
# # ==============================
# print("Step 1: Simple sawtooth pulse")
# set_env(1.0, 0.5, 0.2)  # attack 1s, sustain 0.5s, release 0.2s
# time.sleep(5)
# 
# # ==============================
# # Step 2: Add wobble to volume
# # ==============================
# print("Step 2: Volume wobble (SINE, continuous)")
# wobble("_volume", 0.2, 0.1, 4000)  # depth 0.1, 4s period
# time.sleep(10)
# 
# # ==============================
# # Step 3: Wobble attack envelope
# # ==============================
# print("Step 3: Attack envelope wobble (TRI, sync to env)")
# wobble("_attack", 0.3, 1.7, 20000, shape=1, sync=1)  # 20s triangle
# time.sleep(25)
# 
# ==============================
# Step 4: Trigger-based sequence
# ==============================
print("Step 4: Trigger-based sequence")
set_trigger("step4_ready", True)

my_steps = [
    {
        "set_env_vals": (0.5, 0.5, 0.5),
#        "wobbles": [("_volume", 0.1, 0.2, 5, 0, 2)],
        "cycles": 3,
        "trigger": "step4_ready"
    },
    {
        "set_env_vals": (2.0, 2.0, 2.0),
        "cycles": 5
    }
]

run_sequence_forever(my_steps)
# time.sleep(20)
# stop_sequence()
# 
# # ==============================
# # Step 5: Live-coding REPL example
# # ==============================
# print("Step 5: REPL live-coding example")
# repl_exec("""
# set_freq(660)
# wobble("_freq", 660, 220, 8000)
# """)
# time.sleep(10)
# 
# # ==============================
# # Step 6: Importable procedural sequence
# # ==============================
# print("Step 6: Importable sequence, longer cycles")
# imported_steps = [
#     {"set_env_vals": (2.0, 2.0, 0.5), "cycles": 3},
#     {"set_env_vals": (0.5, 1.0, 0.2), "cycles": 5}
# ]
# run_sequence_forever(imported_steps)
# time.sleep(20)
# stop_sequence()
# 
# # ==============================
# # Wrap up
# # ==============================
# print("Demo finished, fading out volume")
# wobble("_volume", 0.3, -0.3, 5000)  # fade out
# time.sleep(6)
# stop()