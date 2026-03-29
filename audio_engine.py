# audio_engine.py
#
# author      : Werner Thie, wth
#		        ChatGPT, cpt as code companion
# last edit   : wth, 05.03.2026
# mod_history :
#   01.02.2026 - cpt, wth created with pain getting used to the sloppy
#                  overly optimistic mud slinging coding style of the
#                  chat bot. It was a helpful experience but nothing
#                  I (wth) will repeat soon
#   09.02.2026 - wth, spruced up the header comments
#   24.02.2026 - wth, added a rotary switch for volume control, the
#                  code is in audio_vol.py
#   27.02.2026 - cpt, wth switched over from audio_wobble.py to harmonize
# 				   the concepts and move towards a simple DSL
#   05.03.2026 - wth, split into separate files audio_engine.py and
#                  audio_dsl.py as the experiment continues
#
# Threaded infinite-buffer audio generator.
# Baseline for controlled extensions.
#
# Features in THIS FILE ONLY:
#   - carrier frequency control
#   - volume control
#   - burst/pause control
#   - envelope control
#   - rotary encoder for volume
#   - integer wobble engine for modulation
#
# Proven architecture:
#   - blocking i2s.write()
#   - small batch buffer
#   - audio thread does NO parameter math
#   - control thread updates shared state
#
# This has proven to be stable at the upper limit maxing
# out the board completely. Couldn't get the code to run
# stably on the Extensa architecture but didn't investigate
# why the code was so unstable as the sheer additional power
# of two cores, higher clock (240>160MHz), refined coding, etc
# would lead one to expect a much better performance but that
# didn't prove to be real.

from machine import I2S, Pin
import array, _thread, math, time

# ============================================================
# Pin mapping
# ============================================================
BCLK       = Pin(2)
WS         = Pin(3)
DIN        = Pin(4)
SD         = Pin(7, Pin.OUT)   # MAX98357 enable

# rotary encoder (volume) example
ENC_A      = Pin(8, Pin.IN, Pin.PULL_UP)
ENC_B      = Pin(9, Pin.IN, Pin.PULL_UP)

# ============================================================
# Audio constants
# ============================================================
SAMPLE_RATE= 8000
BITS       = 16
LUT_SIZE   = 256

# ============================================================
# User parameters (mutable)
# ============================================================
_freq      = 500        # Hz
_volume    = 0.3        # 0.0 … 1.0
_burst     = 5			# expressed in zero crossings of the
_pause     = 5		    # carrier frequency

# ============================================================
# Shared control state (written ONLY by control thread)
# ============================================================
_phase_inc = 0        # Q32
_amp_q15   = int(_volume * 32767)

# envelope defaults
_attack    = 0.0
_sustain   = 0.0
_release   = 0.0

# envelope runtime state (control thread only)
_env_state = 0      # 0=idle, 1=attack, 2=sustain, 3=release
_env_level = 0.0    # 0.0 … 1.0
_env_t0    = 0      # state start time (ms)
_env_time  = 0.0

# ============================================================
# Precompute sine LUT
# ============================================================
_sine_lut = array.array(
    "h",
    (int(32767 * math.sin(2 * math.pi * i / LUT_SIZE))
     for i in range(LUT_SIZE))
)

# ============================================================
# Infinite buffer with blocking writes
# ============================================================
class InfBuffer:
    def __init__(self, batch=4096):
        self.batch = batch
        self.buffer = array.array("h", [0] * batch)
        self.idx = 0

        self.i2s = I2S(
            0,
            sck=BCLK,
            ws=WS,
            sd=DIN,
            mode=I2S.TX,
            bits=BITS,
            format=I2S.MONO,
            rate=SAMPLE_RATE,
            ibuf=batch * 2
        )
        SD.value(1)

    def write(self, sample):
        self.buffer[self.idx] = sample
        self.idx += 1
        if self.idx >= self.batch:
            self.i2s.write(self.buffer)   # BLOCKING
            self.idx = 0

    def deinit(self):
        try:
            self.i2s.deinit()
        except:
            pass
        SD.value(0)


_playing = False # thread control

# ============================================================
# Audio thread (hard realtime)
# ============================================================
def _audio_thread():
    global _playing, _phase_inc, _burst, _pause, _amp_q15

    ibuf = InfBuffer(batch=1024)

    phase = 0
    PHASE_BITS = 32
    PHASE_MASK = (1 << PHASE_BITS) - 1
    LUT_SHIFT  = PHASE_BITS - int(math.log2(LUT_SIZE))

    env_idx = 0
    prev_sample = 0
    gated = False
    ccnt = 0
    
    while _playing:
        # Sine lookup
        idx = (phase >> LUT_SHIFT) & (LUT_SIZE-1)
        sample = _sine_lut[idx]
        
        # Zero-crossing detection
        crossed = (sample ^ prev_sample) < 0
        prev_sample = sample
        
        if crossed:
            gated = ccnt >= _burst
            
            if gated and ccnt > _pause:
                ccnt = 0
             
            ccnt += 1
           
        if gated:
            ibuf.write(0)
        else:
            # Apply amplitude and envelope
            out = (_amp_q15 * sample) >> 15 # adjust to hardware
            ibuf.write(out)

        # Advance phases
        phase = (phase + _phase_inc) & PHASE_MASK
        env_idx += 1

# ============================================================
# Envelope
# ============================================================
_env_cycle = 0
_env_target_cycle = -1

# Internal flag to mark envelope completion for cycle counting
_env_done = False

def _update_envelope():
    global _env_state, _env_level, _env_t0
    global _env_cycle, _env_target_cycle, _env_done
    global _attack, _sustain, _release
    
    if _attack == 0 and _sustain == 0 and _release == 0:
        _env_state = 0
        _env_level = 1.0
        _env_done = True
        return 1.0

    if _env_done:
        _env_level = 0.0
        _env_state = 0
        return 0.0

    now = time.ticks_ms()
    dt = time.ticks_diff(now, _env_t0) / 1000.0

    finished_cycle = False

    if _env_state == 1:  # attack
        if _attack == 0:
            _env_level = 1.0
            _env_state = 2
            _env_t0 = now
        else:
            _env_level = min(1.0, dt / _attack)
            if _env_level >= 1.0:
                _env_state = 2
                _env_t0 = now
    elif _env_state == 2:  # sustain
        _env_level = 1.0
        if _sustain == 0 or dt >= _sustain:
            _env_state = 3
            _env_t0 = now
    elif _env_state == 3:  # release
        if _release == 0:
            _env_level = 0.0
            finished_cycle = True
            _env_state = 1
            _env_t0 = now
        else:
            _env_level = max(0.0, 1.0 - dt / _release)
            if _env_level <= 0.0:
                finished_cycle = True
                _env_state = 1
                _env_t0 = now
    else:
        _env_state = 1
        _env_t0 = now

    # Cycle counting
    if finished_cycle and _env_target_cycle > 0:
        _env_cycle += 1
        if _env_cycle >= _env_target_cycle:
            _env_state = 0
            _env_level = 1.0
            _env_done = True
            _env_target_cycle = -1  # mark cycles done        
            _attack  = 0
            _sustain = 0
            _release = 0
            
    return _env_level

def _reset_env_cycle():
    global _env_cycle, _env_done
    _env_cycle = 0
    _env_done = False


# ============================================================
# Rotary encoder IRQ (volume)
# ============================================================
def _rotary_irq(pin):
    global _volume
    a = ENC_A.value()
    b = ENC_B.value()
    step = 0
    if a != b:
        step = 1
    else:
        step = -1
    _volume = max(0.0, min(1.0, _volume + step*0.01))

ENC_A.irq(trigger=Pin.IRQ_RISING | Pin.IRQ_FALLING, handler=_rotary_irq)
ENC_B.irq(trigger=Pin.IRQ_RISING | Pin.IRQ_FALLING, handler=_rotary_irq)

# ============================================================
# Control thread (slow, non-realtime)
# ============================================================
def _control_thread():
    global _phase_inc, _amp_q15, _burst, _pause, _volume

    last_freq = None
    last_vol  = None
    last_burst = None
    last_pause = None

    while _playing:
        if _freq != last_freq:
            _phase_inc = int((int(_freq) << 32) / SAMPLE_RATE)
            last_freq = _freq

        env = _update_envelope()
        amp = _volume * env
        if amp != last_vol:
            _amp_q15 = int(amp * 32767)
            last_vol = amp

        _apply_mods()  # wobblers applied here
        time.sleep_ms(25)


# ============================================================
# Public API
# ============================================================
def start():
    global _playing
    if _playing:
        return
    _playing = True
    _thread.start_new_thread(_audio_thread, ())
    _thread.start_new_thread(_control_thread, ())
    print("audio started")

def stop():
    global _playing
    _playing = False
    print("audio stopped")

def set_freq(f=500):
    global _freq
    _freq = int(f)

def set_vol(v=0.3):
    global _volume
    _volume = max(0.0, min(1.0, v))

def set_burst(zero_crossings=5):
    global _burst
    _burst = int(zero_crossings)

def set_pause(zero_crossings=5):
    global _pause
    _pause = int(zero_crossings)

# ============================================================
# Amplitude modulation and envelope shaping
# ============================================================
def set_env(a=0.0, s=0.0, r=0.0, cycle=-1):
    """
    Set envelope parameters with optional cycle count
    cycle=-1: run forever
    cycle=N: run N attack-sustain-release cycles
    """
    global _attack, _sustain, _release
    global _env_state, _env_level, _env_t0
    global _env_target_cycle

    _attack  = max(0.0, float(a))
    _sustain = max(0.0, float(s))
    _release = max(0.0, float(r))
    _env_target_cycle = cycle

    _reset_env_cycle()  # clears _env_cycle and _env_done

    if _attack == 0 and _sustain == 0 and _release == 0:
        _env_state = 0
        _env_level = 1.0
        _env_done = True
    else:
        _env_state = 1
        _env_level = 0.0
        _env_t0 = time.ticks_ms()
        _env_done = False

# ============================================================
# Integer-based modulation for all parameters
# ============================================================
_mods = []          # list of active modulations
_next_mod_id = 1

# Shapes
SINE     = 0
TRI      = 1
SAW      = 2
SQUARE   = 3

# Low-level mod node
def wobble(var, base, depth, period_sec, shape=SINE, cycle=-1):
    """
    Create a modulation node targeting `var`.
    period_sec: modulation period in seconds
    cycle=-1: run forever
    cycle=N: run N LFO cycles
    Returns a unique mod id
    """
    global _next_mod_id
    mod_id = _next_mod_id
    _next_mod_id += 1

    m = {
        "var": var,
        "base": int(base*32767),
        "depth": int(depth*32767),
        "period": max(1, int(period_sec*1000)),
        "shape": int(shape),
        "t0": time.ticks_ms(),
        "id": mod_id,
        "cycle": cycle,
        "done": False
    }
    _mods.append(m)
    return mod_id

def steady(mod_id):
    """Stop a modulation node by id"""
    global _mods
    _mods = [m for m in _mods if m["id"] != mod_id]

# internal helper for integer LFO
def _lfo_value(phase, shape, depth, base):
    """Compute integer LFO value using _sine_lut and integer math"""
    if shape == SINE:
        lut_val = _sine_lut[phase % LUT_SIZE]           # -32767..32767
        v = ((lut_val + 32767) * depth // 32767) + base
    elif shape == TRI:
        if phase < 128:
            v = base + depth * phase // 128
        else:
            v = base + depth * (255 - phase) // 128
    elif shape == SAW:
        v = base + depth * phase // 255
    elif shape == SQUARE:
        v = base + (depth if phase < 128 else -depth)
    else:
        # fallback to sine
        lut_val = _sine_lut[phase % LUT_SIZE]
        v = ((lut_val + 32767) * depth // 32767) + base
    return v

# ============================================================
# Apply modulations (called from control thread)
# ============================================================
_env_prev_state = _env_state  # remember envelope state transitions

def _apply_mods():
    now = time.ticks_ms()

    for m in _mods[:]:
        if m.get("done", False):
            continue

        elapsed = time.ticks_diff(now, m["t0"])
        phase = (elapsed * 256 // m["period"]) & 0xFF

        val = _lfo_value(phase, m["shape"], m["depth"], m["base"])

        # write value
        if m["var"] == "_volume":
            val = max(0, min(32767, val))
            globals()[m["var"]] = val / 32767
        elif m["var"] in ("_attack", "_sustain", "_release"):
            globals()[m["var"]] = val / 32767
        else:
            globals()[m["var"]] = val / 32767

        # manage cycles
        if m["cycle"] > 0:
            prev_phase = m.get("phase_prev", 0)
            # detect full LFO cycle (phase wrap)
            if prev_phase > 240 and phase < 15:
                m["cycle"] -= 1
                if m["cycle"] == 0:
                    m["done"] = True
                    # restore base value on completion
                    globals()[m["var"]] = m["base"] / 32767
                    # remove finished wobble from list
                    _mods.remove(m)

        m["phase_prev"] = phase
        

# ============================================================
# Test sequence
# ============================================================

def test():
    """
    Test the audio engine with a simple envelope and wobble.
    Usage: import audio_engine as a; a.test()
    """
    import audio_engine as a
    
    print("Starting test...")
    a.start()

    try:
        # Envelope: attack=0.5s, sustain=0.5s, release=0.5s, 3 cycles
        set_env(0.2, 0.2, 0.2, cycle=10)

        # Wobble _volume: base=0.6, depth=0.3, period=1s, 2 cycles
        wobble("_freq", 450, 50, 1.0, SINE, cycle=30)

        t0 = time.ticks_ms()
        while time.ticks_diff(time.ticks_ms(), t0) < 40000:
            env_level = _update_envelope()  # get current envelope value
            amp_out = _volume * env_level
            print(f"Frequency: {int(a._freq)}, Envelope: {env_level:.2f}, Amp: {amp_out:.2f}")
            time.sleep(0.25)
    finally:
        print(a._mods)			#should print an empty list
        set_env(0,0,0)  		# reset envelope
        stop()
        print("Test finished.")