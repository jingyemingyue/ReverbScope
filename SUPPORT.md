**English** | [简体中文](SUPPORT.zh-CN.md)

# Getting help and giving feedback

ReverbScope is pre-release software maintained on GitHub. Questions, bug
reports and test results all go through the
[issue forms](https://github.com/jingyemingyue/ReverbScope/issues/new/choose);
each form exists in English and in Simplified Chinese. There is no mailing
list, chat or forum.

| You want to | Use |
| --- | --- |
| Ask how something works, or give general feedback | [Question or feedback](https://github.com/jingyemingyue/ReverbScope/issues/new?template=feedback.yml) |
| Report a crash, an error or wrong behaviour | [Bug report](https://github.com/jingyemingyue/ReverbScope/issues/new?template=bug.yml) |
| Report a number or a validity flag that looks wrong | [Measurement problem](https://github.com/jingyemingyue/ReverbScope/issues/new?template=measurement.yml) |
| Propose a change | [Feature request](https://github.com/jingyemingyue/ReverbScope/issues/new?template=feature.yml) |
| Report a run on a real audio interface | [Audio interface test report](https://github.com/jingyemingyue/ReverbScope/issues/new?template=hardware.yml) |
| Report a run through a DAW | [DAW compatibility report](https://github.com/jingyemingyue/ReverbScope/issues/new?template=daw.yml) |
| Report a security problem | Privately, as described in [SECURITY.md](SECURITY.md); not in a public issue |

## From the desktop app

**Help → Send Feedback...** and **Help → Report a Bug...** open the matching
form in your browser, in the interface language, with the ReverbScope, Python
and Qt versions and the operating system already filled in. The app sends
nothing itself: you see every field in the browser and decide whether to
submit it.

## What helps

* The environment report: **Help → Environment Report for Bug Reports →
  Copy** in the app, or `reverbscope doctor` in a terminal (add `--probe`
  when an audio device is involved). Device names can contain personal
  names; review the text before posting.
* For a measurement question, the session folder or the files you analysed,
  if you can share them.
* Whether the result came from a real interface, a DAW, the synthetic demo
  or the fake backend. Only runs on a physical interface count as hardware
  tests ([docs/HARDWARE_TESTS.md](docs/HARDWARE_TESTS.md)).

Before asking, the [user guide](docs/user-guide/en.md), the
[installation guide](docs/INSTALLATION.md) and its troubleshooting section
answer the most common questions.
