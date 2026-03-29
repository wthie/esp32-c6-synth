# audio_dsl.py
#
# author      : Werner Thie, wth
#               ChatGPT, cpt as code companion
# last edit   : 05.03.2026
# mod_history :
#   05.03.2026 - wth, split from audio_engine.py
#                DSL, sequences, live-coding helpers
#
# Procedural sequence layer (DSL) for audio_engine.py


import time, _thread

import audio_engine as ae

import time, _thread

# ============================================================
# Live-coding helpers / procedural sequences
# ============================================================

_triggers = {}  # named triggers: bool or numeric values

def sleep_until(ms):
    """Sleep until given ms timestamp (ticks_ms compatible)"""
    now = time.ticks_ms()
    dt = time.ticks_diff(ms, now)
    if dt > 0:
        time.sleep_ms(dt)

def set_trigger(name, value=True):
    """Set a trigger variable"""
    _triggers[name] = value

def toggle_trigger(name):
    """Toggle a trigger variable"""
    _triggers[name] = not _triggers.get(name, False)

def sequence_step(set_env_vals=None, wobbles=None, cycles=1, trigger=None):
    """Execute a single procedural step"""
    if trigger is not None:
        while ae._playing and not _triggers.get(trigger, False):
            time.sleep_ms(10)

    # Apply envelope settings
    if set_env_vals:
        a, s, r, c = set_env_vals
        ae.set_env(a, s, r, c)

    # Apply wobblers
    w_ids = []
    if wobbles:
        for w in wobbles:
            # unpack wobble parameters: now cycle replaces sync
            var, base, depth, period_sec, shape, cycle = w
            w_ids.append(ae.wobble(var, base, depth, period_sec, shape=shape, cycle=cycle))

    # Determine hold behavior
    t0 = time.ticks_ms()
    if isinstance(cycles, (int, float)) and cycles > 0:
        # Timed hold in seconds
        t_wait_ms = int(cycles*1000)
        while ae._playing and time.ticks_diff(time.ticks_ms(), t0) < t_wait_ms:
            time.sleep_ms(25)
    else:
        # Wait until envelope and wobblers are done
        while ae._playing and (not getattr(ae, "_env_done", True)
                                    or getattr(ae, "_mods", [])):
            time.sleep_ms(25)

    # Clear wobblers, cycles clear themselves, perpetuals not
    
    print(w_ids)
    for wid in w_ids:
        ae.steady(wid)

# ============================================================
# Threaded sequence runner for live-coded or imported sequences
# ============================================================

_seq_thread = None
_seq_running = False

def _sequence_runner(steps):
    """Internal: loop through steps until _seq_running is cleared"""
    global _seq_running
    while _seq_running and ae._playing:
        for s in steps:
            if not _seq_running or not ae._playing:
                break
            # filter out triggers from kwargs
            kwargs = {k: v for k, v in s.items() if k != "trigger"}
            sequence_step(**kwargs)

def run_sequence_forever(steps):
    """
    Start a sequence in its own thread. Stops previous sequence if running.
    steps: list of dicts with keys for sequence_step() args
    """
    global _seq_thread, _seq_running
    stop_sequence()
    _seq_running = True
    _seq_thread = _thread.start_new_thread(_sequence_runner, (steps,))

def stop_sequence():
    """Stop currently running sequence"""
    global _seq_running, _seq_thread
    _seq_running = False
    _seq_thread = None  # thread will naturally exit

# ============================================================
# REPL / live-coding helpers
# ============================================================

def repl_exec(code_str):
    """
    Execute arbitrary Python code in the context of this module.
    Allows on-the-fly creation of sequences, triggers, wobbles, etc.
    """
    exec(code_str, globals())

def repl_eval(expr_str):
    """
    Evaluate a Python expression in the context of this module
    and return the result.
    """
    return eval(expr_str, globals())


# ============================================================
# DSL convenience layer
# ============================================================

def env(attack=0.0, sustain=0.0, release=0.0, cycles=-1):
    return ("env", (attack, sustain, release, cycles))

def wob(var, base, depth, period_sec, shape=ae.SINE, cycles=-1):
    return ("wob", (var, base, depth, period_sec, shape, cycles))

def hold(cycles=None):
    return ("hold", cycles)

def wait(trigger):
    return ("wait", trigger)

def step(*items, trigger=None):
    s = {"cycles": 1}

    for it in items:
        t, v = it
        if t == "env":
            s["set_env_vals"] = v
        elif t == "wob":
            s.setdefault("wobbles", []).append(v)
        elif t == "hold":
            s["cycles"] = v
        elif t == "wait":
            s["trigger"] = v

    if trigger:
        s["trigger"] = trigger

    return s

# ============================================================
# Test sequences for audio_dsl
# ============================================================
wobble = [
    # Step 1: envelope on _freq, wobble _freq, timed hold 6s
    step(
        wob("_freq", 450, 50, 1.0, ae.SINE, cycles=3),
        hold(6)                                # timed hold
    ),
    # Step 2: envelope on _volume, wobble _volume, wait for cycles
    step(
        wob("_volume", 0.5, 0.2, 0.5, ae.SINE, cycles=3),
        hold()                                 # wait for cycles to end
    ),
]

envelope = [
    # Step 1: envelope on _freq, wobble _freq, timed hold 6s
    step(
        env(0.5, 0.5, 0.5),
        hold(6)                                # timed hold
    ),
    # Step 2: envelope on _volume, wobble _volume, wait for cycles
    step(
        env(0.1, 0.1, 0.1, cycles=10),
        hold()                                 # wait for cycles to end
    ),
]

def test(steps):
    """
    Test the DSL sequencing (see test steps above)
    """
    
    print("Starting DSL sequence test...")
    ae.start()

    run_sequence_forever(steps)	    # start sequence

    # Let it run for a reasonable time, monitoring envelope & wobble
    t0 = time.ticks_ms()
    while time.ticks_diff(time.ticks_ms(), t0) < 40000:
        print(f"Freq: {ae._freq:.1f}, Vol: {ae._volume:.2f}, Env level: {ae._env_level:.2f}, mods: {ae._mods}")
        time.sleep(0.25)

    stop_sequence()
    ae.stop()
    
def complex_test():
    import audio_engine as a
    import audio_dsl as d
    import time

    print("Starting complex DSL sequence test...")
    a.start()

    # Define triggers
    d.set_trigger("start_second_phase", False)

    steps = [
        # Step 1: wobble frequency and volume, timed hold
        d.step(
            d.wob("_freq", 400, 100, 0.8, a.SINE, cycles=5),
            d.wob("_volume", 0.4, 0.3, 1.0, a.TRI, cycles=4),
            d.hold(5)  # timed hold
        ),
        # Step 2: wobble burst and pause while volume envelope runs, wait for cycles
        d.step(
            d.env(0.5, 0.5, 0.5, cycles=3),  
            d.wob("_burst", 3, 2, 1.2, a.SAW, cycles=2),
            d.wob("_pause", 4, 3, 0.7, a.SQUARE, cycles=2),
            d.wob("_volume", 0.6, 0.2, 0.5, a.SINE, cycles=3),
            d.hold()  # wait until wobblers & env complete
        ),
        # Step 3: trigger-based step, only runs when previous step sets trigger
        d.step(
            d.wob("_freq", 500, 80, 0.6, a.TRI, cycles=6),
            d.hold(4),
            trigger="start_second_phase"
        ),
        # Step 4: envelope on frequency and release wobbler on volume, timed hold
        d.step(
            d.env(0.3, 0.7, 0.3, cycles=2),
            d.wob("_volume", 0.5, 0.3, 0.8, a.SAW, cycles=4),
            d.hold(6)
        ),
        # Step 5: set trigger to enable Step 3 and repeat
        d.step(
            d.wob("_freq", 450, 50, 1.0, a.SINE, cycles=2),
            d.wob("_volume", 0.4, 0.2, 1.2, a.TRI, cycles=3),
            d.hold(2),
            d.wait("start_second_phase")
        ),
    ]

    # Start sequence
    d.run_sequence_forever(steps)

    # Monitor parameters
    t0 = time.ticks_ms()
    while time.ticks_diff(time.ticks_ms(), t0) < 60000:
        print(f"Freq: {a._freq:.1f}, Vol: {a._volume:.2f}, Burst: {a._burst}, Pause: {a._pause}, Env level: {a._env_level:.2f}")
        time.sleep(0.25)

    # Stop everything cleanly
    d.stop_sequence()
    a.set_env(0, 0, 0)
    a.stop()
    print("Complex DSL test finished.")
    
    
    
