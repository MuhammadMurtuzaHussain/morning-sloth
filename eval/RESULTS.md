# Evaluation

Everything here ran on the Arduino UNO Q itself: 4 Cortex-A53 cores, 4 GB RAM, llama.cpp's arm64 server image, no GPU. The emails are my real inbox, labelled by hand from sender, subject and preview only. The labelled data stays private and isn't in this repo, so the examples below describe emails rather than quote them.

## Labels

| Level | Meaning | Sloth |
|---|---|---|
| `needs_today` | act or know today | wide awake |
| `soon` | a person wrote, or a deadline this week | one eye open |
| `fyi` | true, nothing to do | asleep |
| `noise` | marketing, digests, codes | asleep |

**Wake vs. quiet** scores only whether the sloth would wake (`needs_today` or `soon`) or stay asleep (`fyi` or `noise`), because that's the decision the matrix shows. Emails I couldn't label confidently, such as a LinkedIn "someone messaged you" digest with no content, are marked ambiguous and left out.

## Sets

- **Design set:** 91 emails, 19 to 22 October 2026, scored on 85. I wrote the code rules after looking at these misses, so these numbers flatter the rules.
- **Held-out set:** 46 emails, 16 to 18 October 2026, scored on 42. I labelled it before running anything and didn't change a rule for it.

## Choosing a model (design set, prompt v1)

| Model | Exact | Wake vs. quiet | needs_today caught | Never said "noise"? | s/email |
|---|---|---|---|---|---|
| Gemma 3 270M Q8 | 7% | 13% | 6/6 | yes, called all 91 "needs_today" | 7.6 |
| Gemma 3 1B Q4_K_M | 12% | 21% | 2/6 | yes, called 67 of 91 "soon" | 38.9 |
| Gemma 4 E2B Q4_0 | 69% | 86% | 1/6 | no, 32 of 35 noise correct | 33.5 |

Gemma 4 E2B "thinks" by default and spent its whole answer budget on reasoning, so every first answer came back empty. With thinking off (`chat_template_kwargs: {enable_thinking: false}` and `--reasoning-budget 0`) it answers in one short JSON object.

## Rules on top of Gemma 4 E2B (prompt v1)

| | Design: exact | Design: wake vs. quiet | Design: today caught | Held-out: exact | Held-out: wake vs. quiet | Held-out: today caught |
|---|---|---|---|---|---|---|
| Gemma alone | 69% | 86% | 1/6 | 64% | 93% | 1/3 |
| + bill, delivery and starting-now rules | 74% | 91% | 5/6 | 64% | 93% | 1/3 |
| + people you've written to | 72% | 88% | 5/6 | 64% | 95% | 1/3, plus 1 woken as soon |

- The bill and delivery rules fired on the design set (two failed electricity top-ups, a parcel arriving today) and had nothing to fire on in the held-out days.
- "People you've written to" rescued a direct request for slides in the held-out set without adding a false wake there. On the design set it added three: a founder's cold email I'd once replied to, a one-word "Excellent." reply and a calendar acceptance.
- A broader "any real person wrote" rule caught more but woke the sloth for 14 emails it shouldn't have, so it was dropped.
- The biggest held-out miss was GitHub's "Possible valid secrets detected" alert, which Gemma called noise. That's why prompt v2 adds a line about security problems with your own accounts or code.

## Prompt v2: the security line (what the device runs now)

Prompt v2 adds one clause to `needs_today`: *a security problem with their own accounts or code (leaked keys or secrets, a sign-in they did not make)*. Both sets were re-run on the board through the device's own Gemma server.

| | Design: exact | Design: wake vs. quiet | Design: today caught | Held-out: exact | Held-out: wake vs. quiet | Held-out: today caught |
|---|---|---|---|---|---|---|
| Gemma alone | 72% | 86% | 1/6 | 60% | 95% | 1/3 |
| + bill, delivery and starting-now rules | 76% | 91% | 5/6 | 60% | 95% | 1/3 |
| **+ people you've written to (the device)** | **74%** | **88%** | **5/6** | **60%** | **98%** | **1/3, and all 3 wake it** |

On the held-out days, every email that needed me that day wakes the sloth:

- GitHub's leaked-secrets alert, which v1 called noise, is now **needs_today**.
- An event "starting in 1 hour" moved from needs_today to **soon**. The sloth still wakes, with one eye instead of two.
- A direct request for slides is raised to **soon** by the people-you've-written-to rule.

The one remaining held-out miss is an automated support-ticket follow-up about my own payment card, which Gemma called fyi. The extra security wording didn't turn ordinary sign-in notices into false alarms: the Ko-fi, Stripe, Luma and Steam sign-in emails all stayed quiet. Exact agreement on the held-out set fell from 64% to 60%, mostly from shuffling between `fyi` and `noise`, which both mean asleep.

Median time per email on the board: 34.5 seconds.

## The setup cap, on the live inbox

Connecting the sloth to Gmail sent three Google alerts: password changed, 2-Step Verification on, and an app password created "for Morning Sloth". Gemma marked both "Security alert" emails `needs_today`. The setup cap in `floors.py` brought them down to `fyi`, and the sloth stayed awake only for the real reasons that night: a failed electricity top-up and a parcel out for delivery.

## Gmail's own Important label, for comparison

On the design set, Gmail marked a Trustpilot review request, a vendor's "[urgent]" incident notice and a product promo as Important, and marked neither failed electricity top-up nor an overnight crash report for a live app as Important.
