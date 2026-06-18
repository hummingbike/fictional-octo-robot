# TODO

> 단계 구분은 [PLAN.md](PLAN.md) 로드맵과 동일. 완료 항목은 `[x]`로 체크.

## Phase 0 — 스파이크 / 기술 검증 ✅ 완료 (2026-06-17)
- [x] 테스트용 텍스트 코퍼스 준비 (`sbsearch.bench.corpus.generate_corpus`, 시드 고정/needle 삽입 지원)
- [x] SQLite FTS5 색인 속도 실측 → 1만 파일/11.9MB 기준 15.7초
- [x] SQLite FTS5 검색 응답시간 실측 (`ripgrep` 풀스캔과 비교) → 평균 0.07ms vs 198.9ms (~2,650배)
- [x] `watchdog`(FSEvents) 이벤트 지연/누락 여부 실측 → 200건 연속, 평균 11.7ms, 누락 0건. 심볼릭 링크 미해결 시 이벤트 0건 전달되는 버그 발견 및 수정
- [ ] 임베딩 모델 후보 2~3개 비교 — **Phase 3로 연기** (torch 등 무거운 의존성, 스파이크 범위에서 제외)
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
- [ ] 주기적 정합성 검사(백그라운드) 추가 검토 — `reconcile_roots`는 이미 구현되어 `sbsearch index`를 cron/launchd로 주기 실행하면 충족 가능하지만, 자동 스케줄링(launchd plist 등) 자체는 미구현. 필요성이 확인되면 Phase 4에서 다룸

## Phase 3 — 시맨틱 검색
- [ ] 청크 분할 전략 결정 및 구현
- [ ] 로컬 임베딩 모델 확정 및 색인 파이프라인에 통합
- [ ] `sqlite-vec` 기반 벡터 저장/조회 구현
- [ ] `--semantic` 검색 모드 CLI 옵션 추가
- [ ] 키워드 검색 결과와 시맨틱 결과 병합/표시 전략 결정

## Phase 4 — 다듬기 / 확장 (옵션)
- [ ] 대용량 단일 log 파일 스트리밍 파싱 / 부분 색인
- [ ] 멀티플랫폼 어댑터 인터페이스 분리 (Linux inotify 등, 구현은 보류)
- [ ] 성능 회귀 테스트(벤치마크 스위트) 자동화

## 문서/기획
- [x] PRD.md 초안 작성
- [x] PLAN.md 초안 작성
- [x] BENCHMARK_EVERYTHING.md 초안 작성
- [x] TODO.md 초안 작성
- [x] Phase 0 실측 결과 반영하여 PRD/PLAN/TODO 수치 업데이트

## 인프라
- [x] GitHub Actions CI 워크플로 추가 (macOS/Linux 매트릭스, pytest 자동 실행)
