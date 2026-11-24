[Türkçe](../tr/formatlar-ve-takvim.md)

# Episode formats, slots and the publishing calendar

A series can make several kinds of episodes (a normal episode, a 30-second short, a swipeable guide…) and post them
in several daily slots. None of this is fixed in code: it lives in `series.json`.

## `formats`

```json
"formats": {
  "main":   {"label": "Episode", "folder": "main", "output": ["video"], "idea_types": ["R", "F"],
             "counter": {"label": "Episode {n}"}, "default": true},
  "short":  {"label": "Shorts", "folder": "short", "output": ["video"], "idea_types": ["S"],
             "words": {"min": 30, "max": 80, "target": "35–70"}, "counter": {"label": "Short {n}"}},
  "guide":  {"label": "Guide", "folder": "guide", "output": ["carousel", "video"], "ready": "any",
             "idea_types": ["G"], "platforms": ["instagram", "tiktok"], "counter": {"label": "Guide #{n}"}}
}
```

| Key | Meaning |
|---|---|
| `label` | name shown in reports and on the screen |
| `folder` | episodes of this format live in `episodes/<folder>/NNN_slug/` (`""`: directly in `episodes/`) |
| `output` | what the format delivers: `video`, `carousel` or both |
| `ready` | `all` (default): every output must exist; `any`: one is enough |
| `idea_types` | idea code prefixes that belong to this format (a new plan for `S-04` is saved under `short`) |
| `words` | narration word limits for this format (otherwise the profile's) |
| `profile`, `profile_overrides` | a different size / subtitle layout for this format |
| `counter` | on-calendar numbering: `{"label": "Short {n}", "start": 1}` (counted in calendar order) |
| `platforms` | where this format is posted (default: `publish.platforms`) |
| `default` | the format of an episode whose folder, plan and idea say nothing |

An episode's format is, in order: its format folder, the plan's `episode_format`, its idea type, the default.
`series formats` lists them with counts per stage; `series formats organize` moves unfiled episodes into their
folders (publish log paths follow); `series formats set 087 short` moves one episode.

## `schedule`

```json
"schedule": {
  "slots": {
    "noon":    {"label": "Noon", "time": "12:00", "days": "daily", "formats": ["short", "guide"],
                "weekday_formats": {"tue": ["guide"]}},
    "evening": {"label": "Evening", "time": "18:00", "days": ["mon", "wed", "fri"], "formats": ["main"]}
  },
  "horizon_days": 28,
  "assume_published": true
}
```

| Key | Meaning |
|---|---|
| `slots.<key>.time` | posting time (series `timezone`) |
| `slots.<key>.days` | `daily` or a list of `mon … sun` |
| `slots.<key>.formats` | formats that air in this slot |
| `slots.<key>.weekday_formats` | optional: which format(s) a given weekday takes (else the format used longest ago) |
| `horizon_days` | how far `series schedule auto` plans by default |
| `assume_published` | a scheduled post whose time has passed counts as published (the scheduler posts on time) |

## Where the calendar comes from

| Status | Source |
|---|---|
| published / scheduled | the publish log (`series publish add`, `series publish sync`) |
| planned | the schedule file (`paths.schedule`, default `publish/schedule.json`), written by `series schedule` |
| empty | a slot day with nothing in it |

```
series calendar                          this week + 3 weeks
series calendar --from 2026-11-16        including history
series calendar --stock                  per slot: ready stock, pipeline, first unplanned day, when the stock runs out
series schedule auto --until 2026-12-31  fill empty slot days with ready episodes (lowest number first)
series schedule add 094 --date 2026-12-01 --slot noon · move · remove · list
series publish sync [--from-file scheduler_export.json]
series views                             views/<status>/<date>_<time>_<format>_<episode> shortcuts
series ui                                the same on a local screen (drag ready episodes onto empty days)
series calendar --html calendar.html     one read-only file of the screen
```

## The local screen

`series ui` starts a small server on `http://127.0.0.1:8765` (only this computer can reach it) and opens the browser.
There is no database: each request reads the series folder, and planning on the screen calls the same code as
`series schedule`, so the folder stays the only source of truth. Tabs: calendar (two-slot week grid, ready stock on
the side, drag to plan, × to unplan), episodes (frames, video, carousel, publish status), stock, ideas, TODO.
