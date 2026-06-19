# TODO

> 단계 구분은 [PLAN.md](PLAN.md) 로드맵과 동일. 완료 항목은 `[x]`로 체크.

## Phase 0 — 스파이크 / 기술 검증 ✅ 완료 (2026-06-17)
- [x] 테스트용 텍스트 코퍼스 준비 (`sbsearch.bench.corpus.generate_corpus`, 시드 고정/needle 삽입 지원)
- [x] SQLite FTS5 색인 속도 실측 → 1만 파일/11.9MB 기준 15.7초
- [x] SQLite FTS5 검색 응답시간 실측 (`ripgrep` 풀스캔과 비교) → 평균 0.07ms vs 198.9ms (~2,650배)
- [x] `watchdog`(FSEvents) 이벤트 지연/누락 여부 실측 → 200건 연속, 평균 11.7ms, 누락 0건. 심볼릭 링크 미해결 시 이벤트 0건 전달되는 버그 발견 및 수정
- [x] 임베딩 모델 후보 2~3개 비교 — **Phase 3로 연기 후 다른 방식으로 해결**: 2~3개 후보 실측 비교 대신, 환경 제약(torch 무거움/Ollama 서버 미설치)이 사실상 후보를 `fastembed` 하나로 좁혀 비교 없이 결정. 근거: [PLAN.md](PLAN.md) 2장, [PRD.md](PRD.md) 10장.
- [x] 실측 결과로 PRD.md 7~8장 수치 보정

## Phase 1 — 키워드 검색 MVP ✅ 완료 (2026-06-18)
- [x] 프로젝트 스캐폴딩 (Python 패키지 구조, `pyproject.toml`, pytest) — Phase 0에서 선구현
- [x] FTS5 인덱서 핵심 로직 (`sbsearch.indexer`) — Phase 0에서 선구현, 단위테스트 포함
- [x] 검색 핵심 로직 + BM25 랭킹 + 검색 연산자 (`sbsearch.search`, FTS5 MATCH 문법 그대로 노출) — Phase 0에서 선구현
- [x] 폴더 등록/제외 패턴 설정 기능 (`.gitignore` 스타일) — `sbsearch.config`(등록/제외 패턴 영속화) + `sbsearch.excludes`(`pathspec` 기반 매칭) + `sbsearch.indexer.index_roots`(다중 루트 색인)
- [x] CLI 엔트리포인트 + `search` 서브커맨드 (`sbsearch search "키워드"`) — `sbsearch.cli`, `root`/`exclude`/`index`/`search`/`status` 서브커맨드
- [x] `status` 서브커맨드: 색인 파일 수 / 마지막 갱신 시각 / 인덱스 크기 — `sbsearch.status.get_status`
- [x] plain/json 출력 옵션, `--limit`, `-C`(컨텍스트 줄 수) — `sbsearch search --json --limit N -C N` (FTS5 snippet 토큰 기준 컨텍스트)

## Phase 2 — 실시간 증분 색인 ✅ 완료 (2026-06-18)
- [x] `watch` 서브커맨드: FSEvents 구독 데몬 (등록 폴더 경로는 반드시 `.resolve()` 후 watchdog에 전달 — Phase 0에서 발견한 심볼릭 링크 버그 참고) — `sbsearch.watcher.IndexWatcher`, CLI `sbsearch watch [--timeout N]`
- [x] 생성/수정/삭제/이동 이벤트별 인덱스 갱신 로직 — `_RootEventHandler` (on_created/on_modified → 재색인, on_deleted → 제거, on_moved → 이전 경로 제거 + 새 경로 재색인)
- [x] 다중 이벤트 디바운싱 (짧은 시간 내 동일 파일 다중 변경 처리) — `sbsearch.watcher.Debouncer` (경로별 타이머 코얼레싱)
- [x] 비정상 종료 후 재시작 시 정합성 복구 (mtime/hash 비교) — `sbsearch.indexer.reconcile_roots` (변경분 재색인 + 삭제된 파일의 잔존 인덱스 항목 제거), `watch`/`index` 커맨드 모두 시작 시 호출
- [x] 주기적 정합성 검사(백그라운드) 추가 검토 — **Phase 4에서 결론**: `reconcile_roots`가 이미 구현되어 있으므로 `sbsearch index`를 cron/launchd로 주기 실행하면 충족됨. 도구 자체에 스케줄러를 내장하지 않고 OS 표준 메커니즘(launchd/cron)에 위임하기로 결정 — 운영 설정은 사용자 환경에 따라 다르므로 도구 범위 밖으로 유지.

## Phase 3 — 시맨틱 검색 ✅ 완료 (2026-06-18)
- [x] 청크 분할 전략 결정 및 구현 — `sbsearch.chunking.chunk_text`(문단 단위 우선, 초과 시 오버랩 슬라이싱)
- [x] 로컬 임베딩 모델 확정 및 색인 파이프라인에 통합 — `fastembed` + `paraphrase-multilingual-MiniLM-L12-v2`(다국어/한국어, 384차원, torch 미사용), `sbsearch.embeddings.LocalEmbedder`
- [x] `sqlite-vec` 기반 벡터 저장/조회 구현 — `sbsearch.semantic`(`enable_vector_search`, `index_file_semantic`, `semantic_search`)
- [x] `--semantic` 검색 모드 CLI 옵션 추가 — `sbsearch search --semantic`, `sbsearch index --semantic`
- [x] 키워드 검색 결과와 시맨틱 결과 병합/표시 전략 결정 — 병합하지 않고 별도 모드로 분리(BM25/코사인 유사도는 척도가 달라 직접 비교 불가, RAG 랭커 없음). 근거: [PLAN.md](PLAN.md) Phase 3.

## Phase 4 — 다듬기 / 확장 (옵션) ✅ 완료 (2026-06-19)
- [x] 대용량 단일 log 파일 스트리밍 파싱 / 부분 색인 — PLAN.md 리스크 표의 "1차" 대응(일정 크기 이상 파일은 색인 제외 옵션)으로 해결: `iter_matching_files`/`index_directory`/`index_roots`/`reconcile_roots`/`IndexWatcher`/시맨틱 색인 모두 `max_file_size_bytes` 지원, CLI `sbsearch index --max-file-size N`, `sbsearch watch --max-file-size N`. 진짜 스트리밍 파싱/부분 색인은 현재 "개인 규모" 목표(PRD 9장)에서 불필요하다고 판단해 보류 — 필요성이 실사용으로 확인되면 재검토.
- [x] 멀티플랫폼 어댑터 인터페이스 분리 (Linux inotify 등, 구현은 보류) — **이미 충족됨**: `watchdog` 라이브러리가 OS별 네이티브 백엔드(macOS FSEvents / Linux inotify)를 런타임에 자동 선택하므로 별도 어댑터 계층이 불필요. CI가 `test_watcher.py`/`test_watch_latency.py`를 macOS+Linux 매트릭스에서 모두 실행해 Linux(inotify) 동작을 이미 검증 중(PR #3/#4에서 ubuntu-latest 통과 확인). 새 코드 추가 없이 기존 설계로 요구사항 충족.
- [x] 성능 회귀 테스트(벤치마크 스위트) 자동화 — `test_search_speedup_meets_prd_m1_target`(PRD M1: ripgrep 대비 5배 이상)과 `test_measure_create_latency_detects_all_file_creations`의 `result.max < 1.0`(PRD NFR: 증분 갱신 지연 1초 이내) 단언을 추가해 모든 CI 실행에서 자동으로 회귀를 감지하도록 함. 1만 파일 규모의 전체 벤치마크는 CI 비용 대비 가치가 낮아 자동화 대상에서 제외, `python -m sbsearch.bench.fts5_vs_ripgrep --num-files 10000` 수동 실행으로 유지.

## 문서/기획
- [x] PRD.md 초안 작성
- [x] PLAN.md 초안 작성
- [x] BENCHMARK_EVERYTHING.md 초안 작성
- [x] TODO.md 초안 작성
- [x] Phase 0 실측 결과 반영하여 PRD/PLAN/TODO 수치 업데이트

## 인프라
- [x] GitHub Actions CI 워크플로 추가 (macOS/Linux 매트릭스, pytest 자동 실행)
