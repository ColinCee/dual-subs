# 0001 Speech-to-text model

## Status

Accepted.

## Context

Episodes have Mandarin audio and English subtitles but no Chinese subtitles, and none could be found online (assrt, SubHD; Bilibili burns its Chinese subtitles into the picture). The Chinese lines have to come from transcribing the audio, locally on an RTX 4090, with timestamps. Anime audio carries music, effects and shouting over the speech.

Shortlisted from published Mandarin results: FireRedASR2 (AED 1B, LLM 8B), Qwen3-ASR-1.7B and Paraformer-large. Dropped without testing: Whisper large-v3 (far weaker on Mandarin, invents lines over music), Dolphin (dialects), Parakeet and Canary (not Mandarin models), paid cloud services (local was wanted).

## Decision

FireRedASR2-AED with FireRedVAD and FireRedPunc, on the raw audio, then a Claude proofread (`proofread.py`) that fixes mishearings using the English line and the cast list as context.

Measured on To Be Hero X E01, all dialogue (0:00 to 21:40), against Bilibili's official Chinese subtitles: 418 lines, 3,430 characters.

| Model | Wrong or missed | Wrong | Missed | Extra | Time on a 4090 |
|---|---|---|---|---|---|
| FireRedASR2-LLM (8B) | 10.3% | 200 | 153 | 460 | 180 s |
| FireRedASR2-AED (1B), chosen | 10.8% | 216 | 156 | 423 | 115 s |
| Paraformer-large | 14.0% | 308 | 172 | 411 | 12 s |
| Qwen3-ASR-1.7B | 30.3% | 494 | 545 | 326 | 32 s |

- The two FireRed models differ by about 20 characters, less than the answer key's own reading errors: a tie, and the 1B model is smaller and faster.
- Qwen3-ASR skipped 18:22 to 21:07 of the long input.
- Decoding is deterministic: three runs on a 90 s clip gave identical text.
- Separating voices from music first (BS-RoFormer) helped Qwen3-ASR and Paraformer on a 90 s clip (11% to 7.5%, 12% to 8%) but made FireRed worse (6% to 7.5%).
- "Extra" is left out of the headline: it is mostly speech Bilibili does not subtitle (嗯, 啊, background voices) and lines the capture missed.
- The proofread, on FireRed's output with the name fixes applied: 10.0% to 8.5-8.7% wrong or missed over three runs (wrong characters 179 to 130-137). Scored one edit at a time, 25-33 per run made a line better and none made one worse; the rest matched lines the key does not cover. About 40 s per episode.

Answer key: Chrome stepped Bilibili's free E01 every 0.5 s and kept a crop of the subtitle band whenever its yellow text changed; RapidOCR read the crops; repeats were merged and times shifted 53.5 s to the local file. The key and the scripts are not kept (the key is Bilibili's subtitle text), so a rerun means capturing it again.

## Consequences

- About a third of FireRed's errors are character names (潇月卿 heard as 萧月清), so each show gets a `names/` file. Most of the rest are same-sounding characters (他/她, 的/得/地) that no audio model can tell apart.
- English song lyrics come out in English; the merge drops lines with no Chinese.
- One episode measured: a show with different audio could rank the models differently.
