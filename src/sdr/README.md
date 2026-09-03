# SDR module — optional, experimental, off by default

The core system (AIS anomaly + official bulletins + weather) needs **no radio
hardware** and no code in this folder. This module is a documented extension for
people who add a receiver later. It is deliberately not wired into `run.py`.

## Design rules (read before enabling)

1. **Receive only.** No transmit, ever.
2. **Permitted frequencies only.** Marine VHF Ch16 (156.800), Ch70 DSC (156.525),
   MF DSC (2187.5 kHz), NAVTEX (518 kHz), amateur/disaster nets, aviation
   emergency. **Never** police / gendarmerie / military. Do not put those in any
   config.
3. **No archive.** Process audio in RAM / `tmpfs`, delete immediately. Persist
   only derived metadata (frequency + timestamp + "activity/keyword"), never a
   transcript of other people's speech.
4. **Never publish raw captures.** No audio clips, no verbatim transcripts to the
   map, the feed, Telegram, or anywhere public. SDR output can only ever raise an
   internal `signal`-level marker for you to verify against official sources.
5. TCK 132 (haberleşmenin gizliliği) + KVKK apply regardless of how you received
   the signal. See the repo README "Legal design" section.

## Preferred signal: DSC, not voice

Digital Selective Calling distress alerts are **structured** — MMSI, GPS position,
nature of distress, machine-readable, no transcription, no interpretation. Far
better precision than Whisper on squelched FM noise, and a much cleaner legal
position (a GMDSS safety broadcast, not a private voice dialogue).

- **VHF Ch70 DSC** — [MattCheramie/GopherTrunk](https://github.com/MattCheramie/GopherTrunk)
  (pure Go, RTL-SDR): FM demod → FFSK → ITU-R M.493 parser. Needs a local VHF antenna.
- **MF DSC 2187.5 kHz** — reachable through a public **KiwiSDR** on the HF band,
  so **no local hardware**. Decode the KiwiSDR audio with
  [alemassimo/TAOSW.DSC_Decoder](https://github.com/alemassimo/TAOSW.DSC_Decoder).
- Test without waiting for a real emergency:
  [kywalda/dsc_generator](https://github.com/kywalda/dsc_generator).

Integration: have the decoder append one JSON object per alert to
`data/dsc_alerts.jsonl` (`{mmsi, lat, lon, nature, ts}`). A small reader (write it
in `run.py` or a sidecar) turns each into an `Incident` with a `Source(kind="dsc")`
→ `classify()` puts it at `probable`.

## NAVTEX (maritime safety information)

- [pd0wm/navtex](https://github.com/pd0wm/navtex) (Python) via a KiwiSDR 518 kHz
  audio stream (`kiwiclient/kiwirecorder.py --nc`).
- Or skip radio entirely: NAVAREA III / METAREA warnings are published as text by
  hydrographic offices — scrape them and emit `Warning(kind="navtex")`.

## Voice → Whisper (last resort, keyword screening only)

- [Nite01007/RadioTranscriber](https://github.com/Nite01007/RadioTranscriber) is
  ~80% of this: live scanner audio → faster-whisper (CTranslate2 INT8), WebRTC
  VAD, runtime squelch. Fork it; point it at Ch16.
- `whisper.cpp` (`ggml-small`, `-l tr`) is the low-RAM alternative for a Pi.
- Expect hallucinations on noisy NFM. Treat every hit as unverified. Write hits to
  `data/sdr_hits.jsonl` (`{freq, ts, keyword, confidence}`) — metadata only, no
  transcript text leaves the box.
- `sentinel_stub.py` in this folder is a minimal reference (WAV in → keyword out),
  clearly marked experimental. It is not imported anywhere.

## Eval

Build a small labelled corpus (your own voice reading distress phrases + SoX radio
noise; archived SAR audio for offline WER only — do not republish clips). Report
WER and keyword recall/precision in `WRITEUP.md`. That number is the honest measure
of whether the voice path is worth running at all.
