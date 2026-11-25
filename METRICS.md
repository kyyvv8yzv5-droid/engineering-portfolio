# Measurement method

Metrics come from Git blobs at the full pinned commits listed below. A source line is a physical, nonblank text line, including comments. These are reproducible size measurements, not logical statement counts or effort estimates.

Application counts include recognized implementation languages, SQL migrations, shell scripts and web markup. Tests are separated by path or file naming, and counted independently. Markdown documentation and configuration are reported separately. Exclusions include archived releases, runtime data, generated inventories, minified assets, lockfiles, dependencies, vendored material, binary media and model artifacts, disposable fixtures, and reusable project templates.

Python classes, functions, and test functions are counted from ASTs. Other named class or actor and function declarations, JS/TS test calls, and Swift test functions use conservative declaration matching. They omit some methods, factories, dynamic cases and parameterized expansion. Source test definitions are not test run totals. Module counts are implementation file counts excluding Python package initializers and non-module markup, configuration and migrations.

Route counts cover unique file, decorator, and fixed route declarations from Python application/router decorators and conventional Next.js handler declarations. Dynamically registered or computed routes may be absent, and a Next.js proxy definition is not a count of the proxied API. SQLite counts are unique statically detected CREATE TABLE names, independent of installed database state or migration variants.

Dependencies are direct declarations detected in Python project/requirements manifests and package.json, without lockfile transitives, system tools or editable local links. Commit counts are commits reachable from each pinned commit in its local Git repository. Clean import snapshots naturally have shorter history than their development repositories.

Published lines are the nonblank lines in the previously approved excerpts. Proposed lines include those excerpts plus candidate modules. Code coverage percentages use non-test excerpts and non-test candidate lines over application source lines. Overlap is subtracted when a candidate contains the same original excerpt. This percentage measures footprint, not test coverage or feature completeness.

## Before and after

| Application | Published files | Proposed files | Published lines | Proposed lines | Total application lines | Published application represented | Proposed application represented |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| SLEEP | 1 | 13 | 5 | 858 | 15,614 | 0.03% | 3.96% |
| AuthenticityAI | 1 | 13 | 18 | 1,283 | 25,597 | 0.07% | 3.83% |
| Picker | 3 | 22 | 57 | 1,153 | 1,553 | 3.67% | 61.69% |
| Culinary IQ | 3 | 17 | 39 | 1,628 | 17,685 | 0.22% | 7.87% |

## SLEEP

Pinned commit: f48707ab18e914a100f9748605997cbfd745271e.

| Category | Files | Nonblank lines |
| --- | ---: | ---: |
| application | 138 | 15,614 |
| test | 59 | 5,300 |
| documentation | 64 | 2,047 |
| configuration | 5 | 2,185 |

Application modules: 93. Python classes and functions: 172 and 753. Other detected named class/actor and function declarations: 1 and 193.

Static routes: 137. SQLite table names: 19. Reachable Git commits: 1.

Test definitions: Python 334, JS/TS 0.

Language lines: Python 12,468, JavaScript 1,890, CSS 813, HTML 443.

Detected dependencies: fastapi, httpx, pydantic, pytest, python-dotenv, uvicorn.

[Open module collection](projects/sleep/source/README.md).

## AuthenticityAI

Pinned commit: 1cb33a7af7594430733c04e44d198b579766457d.

| Category | Files | Nonblank lines |
| --- | ---: | ---: |
| application | 188 | 25,597 |
| test | 38 | 9,112 |
| documentation | 78 | 5,430 |
| configuration | 15 | 853 |

Application modules: 165. Python classes and functions: 144 and 1063. Other detected named class/actor and function declarations: 0 and 44.

Static routes: 75. SQLite table names: 26. Reachable Git commits: 1.

Test definitions: Python 430, JS/TS 28.

Language lines: Python 24,435, JavaScript 601, CSS 455, PowerShell 106.

Detected dependencies: Pillow, fastapi, mediapipe, numpy, opencv-contrib-python, python-multipart, reportlab, uvicorn.

[Open module collection](projects/authenticityai/source/README.md).

## Picker

Pinned commit: c2fa78a48d2fc867cff85dd02f7219d3dae760ad.

| Category | Files | Nonblank lines |
| --- | ---: | ---: |
| application | 30 | 1,553 |
| test | 4 | 305 |
| documentation | 4 | 165 |
| configuration | 8 | 269 |

Application modules: 20. Python classes and functions: 61 and 61. Other detected named class/actor and function declarations: 3 and 12.

Static routes: 0. SQLite table names: 0. Reachable Git commits: 1.

Test definitions: Swift 6, Python 33.

Language lines: Python 1,225, Swift 315, HTML 13.

Detected dependencies: httpx, pillow, pydantic, pytest.

[Open module collection](projects/picker/source/README.md).

## Culinary IQ

Pinned commit: 1c7febcbef4a7de39ae9877502994ecbeb268968.

| Category | Files | Nonblank lines |
| --- | ---: | ---: |
| application | 177 | 17,685 |
| test | 20 | 3,320 |
| documentation | 17 | 699 |
| configuration | 11 | 329 |

Application modules: 142. Python classes and functions: 222 and 710. Other detected named class/actor and function declarations: 5 and 329.

Static routes: 145. SQLite table names: 66. Reachable Git commits: 1.

Test definitions: JS/TS 8, Python 178.

Language lines: Python 10,816, TypeScript TSX 3,677, PowerShell 1,093, SQL 1,058, TypeScript 884, CSS 122, JavaScript 25, Batch 10.

Detected dependencies: PyJWT, class-variance-authority, clsx, eslint, eslint-config-next, eslint-plugin-jsx-a11y, eslint-plugin-react, eslint-plugin-react-hooks, fastapi, framer-motion, httpx, lucide-react, next, numpy, opencv-python, picker, pillow, pydantic-settings, pytest, python-multipart, react, react-dom, tailwind-merge, tailwindcss, typescript, uvicorn.

[Open module collection](projects/culinary-iq/source/README.md).
