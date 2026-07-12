# sbsearch — 개빠름 메모검색

여러 폴더에 흩어진 텍스트 문서(`.txt` / `.md` / `.log`)를 미리 색인해 두고, 키워드를 입력하면 [Everything](https://www.voidtools.com/)급 속도로 **파일 내용**을 찾아주는 CLI 검색 도구입니다. 파일이 바뀌면 인덱스가 실시간으로 따라옵니다.

- **빠름**: SQLite FTS5 인덱스 기반. 1만 파일 코퍼스 실측에서 평균 0.07ms — `ripgrep` 풀스캔 대비 약 2,650배 (상세: [BENCHMARK_EVERYTHING.md](BENCHMARK_EVERYTHING.md))
- **실시간**: `watch` 데몬이 생성/수정/삭제/이동을 감지해 1초 이내에 인덱스 반영 (macOS FSEvents / Linux inotify 자동 선택)
- **한국어 친화**: `예산안`으로 검색하면 `예산안을`, `예산안이` 같은 조사 붙은 형태도 찾습니다
- **시맨틱 검색(옵션)**: 로컬 임베딩 모델로 키워드가 정확히 일치하지 않아도 의미가 비슷한 메모를 찾습니다. 외부 API 전송 없음 — 개인 메모가 밖으로 나가지 않습니다

## 요구 사항

- Python 3.10+
- macOS 또는 Linux
- SQLite FTS5 지원 빌드(macOS는 Homebrew Python 권장 — 시스템 Python은 sqlite3 확장 로딩이 제한될 수 있음)

## 설치

```bash
git clone https://github.com/hummingbike/fictional-octo-robot.git
cd fictional-octo-robot
python3 -m venv .venv && source .venv/bin/activate
pip install .
```

설치하면 `sbsearch` 명령이 생깁니다.

## 빠른 시작

```bash
# 1. 검색할 폴더 등록 (여러 개 가능)
sbsearch root add ~/notes
sbsearch root add ~/work/meeting-logs

# 2. 색인에서 뺄 패턴 등록 (.gitignore 스타일, 선택)
sbsearch exclude add "drafts/"
sbsearch exclude add "*.tmp.md"

# 3. 최초 색인
sbsearch index

# 4. 검색!
sbsearch search "예산안"
sbsearch search "disk AND full" --limit 5
```

파일 변경을 실시간으로 반영하려면 터미널 하나에 감시 데몬을 띄워 둡니다:

```bash
sbsearch watch    # Ctrl+C로 종료
```

`watch`는 시작할 때 이전 실행 이후의 변경분을 자동으로 따라잡으므로(정합성 복구), 항상 켜 둘 필요는 없습니다. 켜 두지 않는다면 `sbsearch index`를 주기적으로(cron/launchd 등) 실행해도 됩니다.

## 검색 문법

연산자 없이 입력하면 단어별 **접두사 매칭**으로 동작합니다 — `예산안`이 `예산안을`에, `log`가 `logging`에 매칭됩니다. 여러 단어는 모두 포함(AND)으로 해석됩니다.

FTS5 질의 문법을 그대로 쓸 수도 있습니다(따옴표·연산자·와일드카드가 하나라도 있으면 재작성 없이 그대로 전달):

```bash
sbsearch search '"세컨드 브레인"'        # 구문 검색 (정확한 어순)
sbsearch search 'apple NOT banana'      # 연산자 (AND/OR/NOT, 대문자)
sbsearch search '회의* OR 미팅*'         # 접두사 와일드카드 직접 지정
```

출력 옵션:

```bash
sbsearch search "키워드" --limit 10    # 결과 개수 제한 (기본 20)
sbsearch search "키워드" -C 30         # 스니펫 컨텍스트 폭 (토큰 수, grep -C 유사)
sbsearch search "키워드" --json        # JSON 출력 (스크립트 연동용)
```

## 시맨틱 검색 (옵션)

키워드가 겹치지 않아도 의미로 찾고 싶을 때 사용합니다. 로컬 임베딩 모델(`fastembed` + `paraphrase-multilingual-MiniLM-L12-v2`, 다국어/한국어 지원)을 쓰며, 최초 실행 시 모델(~220MB)을 내려받습니다.

```bash
sbsearch index --semantic                          # 시맨틱 인덱스 구축
sbsearch search --semantic "예산 관련 회의 내용"    # 의미 기반 검색
```

키워드 결과와 병합되지 않고 별도 모드로 동작합니다(BM25와 코사인 유사도는 척도가 달라 직접 비교하지 않는다는 설계 결정 — [PLAN.md](PLAN.md) Phase 3).

## 명령어 요약

| 명령 | 설명 |
|---|---|
| `sbsearch root add/remove/list <path>` | 검색 대상 폴더 등록/해제/목록 |
| `sbsearch exclude add/remove/list <pattern>` | `.gitignore` 스타일 제외 패턴 관리 |
| `sbsearch index [--semantic] [--max-file-size N]` | 전체 색인 구축/갱신 (변경분만 재색인, 삭제 파일 정리 포함) |
| `sbsearch watch [--timeout N] [--max-file-size N]` | 실시간 감시 데몬 (시작 시 정합성 복구 후 감시) |
| `sbsearch search <query> [--semantic] [--json] [--limit N] [-C N]` | 검색 |
| `sbsearch status` | 색인 파일 수 / 마지막 갱신 시각 / 인덱스 크기 |

`--max-file-size N`(바이트)을 주면 그보다 큰 파일(예: 거대 로그)은 색인에서 건너뜁니다.

## 설정과 데이터 위치

- 설정: `~/.sbsearch/config.json` (등록 폴더, 제외 패턴, 인덱스 경로)
- 인덱스: 설정 파일 옆의 `index.db` (SQLite 단일 파일)
- 모든 명령에 `--config <path>`를 주면 다른 설정 파일을 쓸 수 있어, 용도별로 독립된 인덱스를 여러 개 운용할 수 있습니다

## 개발

```bash
pip install -e ".[dev]"
pytest                    # 단위테스트 + 성능 회귀 게이트 (macOS/Linux CI와 동일)
python -m sbsearch.bench.fts5_vs_ripgrep --num-files 10000   # 대규모 벤치마크 (수동)
```

설계 배경과 로드맵은 [PRD.md](PRD.md), [PLAN.md](PLAN.md), [TODO.md](TODO.md)를 참고하세요.

## 라이선스

[Apache-2.0](LICENSE)
