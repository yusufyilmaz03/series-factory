# Job queue (`series jobs`)

Long commands (assemble with effects, batch, voice) need the computer that owns the series folder: its Python, its
tools, its speed. A remote session, such as a phone chat or a sandbox that only sees the folder, can write files but
cannot keep a render running. The job queue connects the two.

```
series ui                                  # on the series computer: the screen + the job worker
series jobs add assemble 013               # from anywhere that can write the folder
series jobs add batch 013-018 --only assemble
series jobs list                           # state: queued, running, done, failed, cancelled, interrupted
series jobs log <id> [--tail 80]
series jobs cancel <id>
series jobs worker                         # the worker without the screen (for a login item or launchd)
```

- A job is `<preview>/jobs/<id>.json`; its output goes to `<id>.log` beside it.
- The worker runs one job at a time, oldest first. `batch` parallelises inside itself.
- Jobs are series commands given as words, never a shell line. `ui`, `jobs`, `init` and `migrate` are refused.
- A job left running when the worker stopped is marked `interrupted`; queue it again.
- In `series ui` the **Jobs** tab queues a command, shows the queue with the last log lines and stops a job.
- `series ui --no-jobs` opens the screen without the worker.
- Options of `list`, `log` and `cancel` may follow the operation. For `add`, put `--json` before it:
  `series jobs --json add status`.
