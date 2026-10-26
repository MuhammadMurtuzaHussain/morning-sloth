# Demo guide: watch the AI wake the sloth

Two emails and one terminal command. Everything runs on the board; your computer only watches over `adb`.

## 1. Start the live view

```bash
python3 tools/demo.py watch
```

It shows each step as it happens: the email arriving, Gemma 4 thinking on the board (with a running timer), the code rules, and the flag the sloth raises, drawn with the same pixels as the matrix. Sender addresses show as `…@gmail.com`; add `--full` for the whole address.

## 2. Send the two emails

Send both **from the sloth's Gmail account to itself** (compose in Gmail, put your own address in To). That address is in `EXTRA_CONTACTS`, so it counts as someone you've written to.

| Face | Subject | Body | Why it works |
|---|---|---|---|
| **One eye open** (`peek`) | `Quick question for tomorrow` | `Could you send me the slides before tomorrow's meeting? No rush tonight.` | From someone you've written to, so the code rules give at least *soon*. |
| **Wide awake** (`awake`) | `Webinar starting in 10 minutes` | `The Morning Sloth launch webinar is starting in 10 minutes. Join now.` | "Starting in N minutes" always gives *needs_today*, whatever Gemma says. |

Or let the board send them for you:

```bash
python3 tools/demo.py peek
python3 tools/demo.py awake
python3 tools/demo.py asleep   # marks the demo emails read: back to sleep
```

`python3 tools/demo.py emails` prints both again.

## 3. What you'll see

```
00:31:02  📬  new email  Webinar starting in 10 minutes  from …@gmail.com
          …  Gemma is thinking on the board, 34s
00:31:36  🧠  Gemma 4 says  noise  (34s, on the board)
00:31:36  ⚖️   code rules raise it to  needs_today  because an event is starting now
00:31:36  🦥  FLAG → awake  WIDE AWAKE, it needs you today
```

Allow about a minute for the poll (`POLL_MINUTES=1`) plus about 35 seconds for Gemma. Cut the wait in the edit.

## Before you film

- The matrix is dark from `QUIET_FROM` to `WAKE_AT` (02:00 to 06:00 by default). Film outside it, or set `QUIET_FROM=23:59` in `secrets.env` and restart.
- Start asleep: mark any unread mail as read first (`python3 tools/demo.py asleep` only clears the demo emails).
- The bus countdown shows only from 09:00 to 13:00. At any other hour you get just the faces.
- Keep the Terminal's width at 80 columns or more, and lights low so the matrix reads on camera.
