# TiMotion TWD1 Bluetooth protocol

What the TiMotion **TWD1** Bluetooth module speaks, as used by the *Stand Up Pls*
phone app and by many desk brands that build on TiMotion parts. This is the
reference the integration is written against, so each statement says how it was
established.

Evidence levels used below:

- **Verified** — observed on a real desk (Ergonice frame, TiMotion TC15S-Z73
  control box, TDH18P handset, TWD1 module).
- **App** — read from the phone app's own code (the Stand Up Pls APK, decompiled
  from a copy installed on the author's phone, for interoperability; none of its
  code is included here).
- **Derived** — follows from the two above but was not exercised on its own.

## Transport

A Bluetooth LE peripheral that advertises as `stand UP- NNNN` (four digits) with
the Nordic UART Service. **Verified.**

| | UUID | Properties |
|---|---|---|
| Service | `6e400001-b5a3-f393-e0a9-e50e24dcca9e` | |
| Notify (desk → host) | `6e400003-…` | notify |
| Write (host → desk) | `6e400002-…` | write, write without response |

There are no readable characteristics. The module accepts **one connection at a
time**: while the phone app (or this integration) is connected the desk stops
advertising.

It sends nothing until it has received a first frame. After any frame it streams
status at roughly 10 frames per second for as long as the link stays up. **Verified.**

## Frames

All frames are 5 bytes. The last byte is a checksum:

```
checksum = (byte0 + byte1 + byte2 + byte3) & 0x7F
```

The mask is **0x7F, not 0xFF**. It only differs when the byte sum has bit 7 set,
which is why most frames look as if a plain 8-bit sum would do. The reset-mode
status frames and the stop frame are where it matters. **Verified** (all captured
status frames and all tested command frames) and **App** (`WorkQueueKt.MASK` is 127).

### Commands (host → desk)

```
D9 FF <cmd> <arg> <checksum>
```

| cmd | meaning | arg | evidence |
|---|---|---|---|
| `00` | stop / "just give me status" | `00` | Verified |
| `01` | up (keep sending while you want to move) | `00` | Verified |
| `02` | down (same) | `00` | Verified |
| `03` | **reset** (re-measure the lowest height, see below) | `00` | App; the same state was entered from the handset (Verified) |
| `04` | move to a height | height in cm | Verified (130 → 74 cm) |

Resulting fixed frames: stop `D9 FF 00 00 58`, up `D9 FF 01 00 59`,
down `D9 FF 02 00 5A`, reset `D9 FF 03 00 5B`, and for example 74 cm
`D9 FF 04 4A 26`.

**The desk behaves like a handset button.** It keeps moving only while it keeps
receiving command frames. The app resends every 100 ms and, when the user lets go,
sends stop frames for about 600 ms. Move-to-height works the same way: resend the
`04` frame until the desk reports idle at the target.

The `arg` byte of up/down is ignored by the module (older write-ups pass the last
height there; zero works).

### Status (desk → host)

```
99 <status> <height hi> <height lo> <checksum>
height_cm = ((hi << 8) | lo) - 256
```

| status | meaning | evidence |
|---|---|---|
| `40` | idle | Verified |
| `41` | moving down | Verified |
| `42` | moving up | Verified |
| `51` / `52` | down / up **with the anti-collision flag** (bit 4, `0x10`) | Verified |
| `03` | height-reset mode; height field is the sentinel `01 FF` | Verified |

Bits: `0x40` always set, `0x01` down, `0x02` up, `0x10` collision (T-Touch
sensor tripped). On a collision the desk reverses a few centimetres, pauses, then
the move can resume; one captured example went `0x41` → `0x51` → `0x52` (up 3 cm)
→ idle → `0x41`.

Height calibration points (**Verified**): lowest 65 cm = raw `0x0141`; 74 cm =
`0x014A`; 111 cm = `0x016F`; factory top 130 cm (stops by itself). A desk that has
just been reset reports from 65 cm.

#### Reset mode

Entering the handset's reset sequence (both arrows held) produces `99 03 01 FF 1C`
(three times in one capture), followed by moves with the sentinel height while the
box drives to its lowest point and re-measures. Afterwards heights restart at the
bottom (65 cm). Memory slots were kept across a reset on the tested desk. The
phone app holds its Reset button the same way as a handset: it sends `03`
repeatedly while pressed.

## What is *not* exposed

Everything below lives in the control box / handset and **cannot be read or set
over this module**:

- the handset's memory slots (M1…M3),
- upper and lower travel limits (factory limit on the tested desk: 130 cm),
- collision sensitivity,
- the display unit.

Evidence: the module has only one write and one notify characteristic; it
answered the phone app's own "send me everything" frame (`DD 01 00 00 00 00 00 00`)
with an ordinary status frame and nothing else (**Verified**).

The phone app's own "M1/M2" are numbers stored on the phone (`SharedPreferences`
keys `m1`/`m2`); it drives to them with the move-to-height command (**App**). They
are unrelated to the handset's slots.

### Protocol 2

Newer modules speak a richer protocol the app also understands (**App**, not seen
on a real desk): frames start with `9D`, are 11 / 14 / 19 bytes long (byte 1 =
`00` settings, `01` status 1, `02` status 2) and carry product id, minimum and
maximum height, battery, motor and T-Touch flags, error codes, **limits and the
four memory heights**. It is requested with `DD 01 00 00 00 00 00 00` and uses a
7-bit checksum over bytes 2…n-2. A desk that speaks it would let this integration
read its slots; PRs with captures are welcome.

## Handset serial line (not Bluetooth)

For comparison: the handset itself talks to the control box over a serial line
(9600 baud in the community TC15 controller project, frames like
`D8 D8 FF 02 02` for up). That is a different layer from the Bluetooth module
described here and would be the way to see the handset's M buttons; it needs
hardware spliced onto the handset cable and is out of scope for this integration.

## Safety notes found the hard way

- Never send `03` while experimenting: it starts a reset.
- A frame with a wrong checksum is silently ignored, which also means a "stop"
  built with the 8-bit mask (`…D8`) does nothing. Always send `D9 FF 00 00 58`.
- A desk that did not move after a command is almost always one that is already at
  its limit, or one whose Bluetooth link is held by another client.
