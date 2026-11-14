# 개인 포크의 Windows 개발 환경

대상은 `kinghuijae/Madeira`, 작업 폴더는 `C:\personal_projects\Madeira`이다.
Windows에서는 소스 수정, Git 작업, Python 검사와 게임 실행 파일의 정적 분석을
진행한다. IPA는 기존 GitHub Actions의 macOS/Xcode 환경에서 만든다.
WSL이나 Docker도 Apple의 iOS SDK와 Xcode를 대신하지 않는다.

## 설치된 환경과 재설정

2026-11-14에 포크의 `main` 커밋
`fbad430410b4075192166172447c859714726de9`를 복제했다.
Git for Windows 2.51.0, uv 0.12.17을 사용했고 PowerShell 7.6.9와
Windows 기본 PowerShell 5.1에서 설정·검사 스크립트를 검증했다.
Python 3.12.14를 저장소의 `toolchains/python`에 설치해 `.venv`를 만들었다.
아래 검사는 Python 표준 라이브러리만 사용하므로 pip 패키지가 필요 없다.

```powershell
Set-Location C:\personal_projects\Madeira
.\tools\setup-windows.ps1
.\tools\check-windows.ps1
```

설정 스크립트는 Git for Windows와 uv가 설치되어 있다고 가정한다.
Python 설치·캐시 경로는 이 저장소에만 적용하며 시스템 PATH를 수정하지 않는다.
이미 서브모듈을 받았다면 `-SkipSubmodules`, Python 환경도 준비됐다면
`-SkipPython`을 사용할 수 있다. 다운로드는 최초 실행 시 네트워크가 필요하다.
검사 로그는 Git에서 제외된 `.local/checks`에 남는다.

FEX, Wine, DXMT, Madeira Dock 및 중첩 의존성까지 총 24개 서브모듈을
저장소가 지정한 커밋으로 초기화했다. `--depth 1`로 받은 의존성은 과거 기록이
필요할 때 추가 fetch가 필요할 수 있다. `submodule update --remote`는 사용하지 않는다.

## 원본으로의 푸시 차단

- `origin`: 개인 포크 `https://github.com/kinghuijae/Madeira.git`.
- `upstream`: 원본을 fetch할 수 있지만 push URL은 `DISABLED`.
- 기본 push 대상은 `origin`, `push.default`는 `simple`.
- `core.hooksPath=.githooks`로 기존 훅을 활성화했다.
- `pre-push`는 `upstream`이라는 remote와 `github.com`의 `willfaust/*`
  목적지를 거부한다. HTTPS, SCP 형식 SSH, `ssh://`, 명시적 포트와 대소문자 변형도 검사한다.
  기존 라이선스 초안 검사도 유지한다.
- 모든 초기화된 서브모듈에도 동일한 훅을 연결하고 `origin`의 push URL을
  `DISABLED`로 설정했다. 원본 소스 다운로드에는 영향이 없다.

훅은 실수 방지용 로컬 설정이다. `--no-verify`, Git 설정 변경, 다른 clone이나
GitHub 웹에서 하는 변경까지 막지는 않는다. 새 clone에서는 설정 스크립트를
다시 실행해야 한다. 서브모듈 자체를 수정해 CI에서 사용하려면 해당 의존성도
개인 계정에 포크한 뒤 `.gitmodules` URL과 커밋 핀을 함께 변경해야 한다.
서브모듈의 push URL도 그 개인 포크로 별도 설정해야 한다. 이 초기 설정
스크립트를 다시 실행하면 서브모듈 push는 다시 일괄 차단된다.

## 로컬 검증 범위

`check-windows.ps1`은 다음을 실제 실행한다.

| 검사 | 범위 |
| --- | --- |
| CI component keys | 4,119개 소스 변경 조합의 캐시 무효화 규칙 |
| CI release | 포크·브랜치·이벤트·작업 결과별 자동 게시 허용 조건 |
| Game dependencies | PE32/PE32+ 일반·지연 DLL import 파싱 |
| Wine media DLLs | 미디어 DLL 패키징 검사와 잘못된 PE 입력 |
| Font keys / NLS | 폰트 등록 복구 및 추가 코드페이지 경로 |
| Config catalog | 생성된 설정 카탈로그의 일치 여부 |
| Translations / doc links | 번역 카탈로그와 문서 내부 링크 |
| Prefix template | 빌드 머신을 가리키는 절대 심볼릭 링크 없음 |
| pre-push | 실제 Git 훅 실행으로 10가지 허용·차단 목적지 확인 |
| Shell syntax | 빌드 도구 및 훅 20개의 Bash 문법 |

Windows 경로의 역슬래시 때문에 설정 카탈로그가 잘못 달라지던 부분은
`build/tools/gen-config-catalog.py`에서 저장소 경로를 `/`로 정규화하도록 수정했다.
생성된 Swift 파일 자체는 바꾸지 않았다.

Swift 컴파일 검사는 로컬에서 실행하지 않는다. CI의 `plan`에는 POSIX shell
fixture, Apple `plutil`/`xcrun`, Swift가 필요한 검사도 있어 Windows 검사와 범위가
다르다. `tools/build-ipa.sh`를 Git Bash로 실행하면 macOS/Xcode 필요 오류로
종료하는 것도 확인했다. 로컬 검사가 통과해도 iPhone 게임 호환성을 뜻하지 않는다.

## 기존 CI 사용

워크플로는 [Build IPA](https://github.com/kinghuijae/Madeira/actions/workflows/build.yml)다.
기존 빌드와 캐시 흐름을 유지하고, 성공한 IPA를 게시하는 `release` 작업을 추가했다.

- `main`, `codex/pr-build-*`에 push하거나 포크 내부 PR을 갱신하면 실행된다.
- 다른 이름의 개발 브랜치는 Actions의 **Run workflow**에서 선택해 실행한다.
- 원본 저장소에 PR을 만들 필요가 없다. PR을 쓸 경우 base 저장소도 개인 포크로 선택한다.
- 현재 `xcode-27`은 [GitHub 공식 macOS ARM64 러너](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)다.
- 기본 워크플로 권한은 `contents: read`이고 `release` 작업에만 `contents: write`를 준다.
  자동 제공되는 `GITHUB_TOKEN`으로 게시하므로 개인 PAT나 Apple 인증서 secret을
  추가할 필요가 없다.
- IPA는 ad-hoc 서명 후 `Madeira-ipa` artifact로 업로드된다. iPhone 설치 시에는
  본인 Apple ID를 사용하는 사이드로딩 도구의 재서명과 JIT 설정이 별도로 필요하다.
- 첫 실행은 포크 자체의 캐시가 없어 오래 걸린다. 이후 성공한 구성 요소의 캐시를 재사용한다.

### IPA 자동 릴리스

`kinghuijae/Madeira`의 `main`에 push하거나 `main`에서 **Run workflow**를 실행하면,
`app` 빌드 또는 완성된 IPA를 복원하는 `reuse`가 성공한 뒤
[Releases](https://github.com/kinghuijae/Madeira/releases)에 **Pre-release**가 생성된다.
PR, 다른 브랜치·저장소, 실패·취소된 빌드에서는 게시하지 않는다.

- 태그: `ci-<실행 번호>-<재시도 번호>-<커밋 앞 7자리>`.
- 첨부 파일: `Madeira.ipa`, `SHA256SUMS`.
- 릴리스 노트: 소스 커밋, CI 실행 링크, IPA SHA-256.
- 다운로드한 해당 실행의 artifact를 소스 트리·런타임 입력·바이너리 구조까지 검증한다.
  초안 릴리스에 업로드한 후 서버의 IPA 크기와 SHA-256을 대조하고 공개한다.
- 기존 릴리스를 덮어쓰지 않고, 정식 Latest 릴리스로 지정하지 않는다.
  업로드가 실패하면 초안만 남을 수 있으며 **Re-run jobs**는 새 재시도 태그를 사용한다.

`Madeira-ipa` Actions artifact도 계속 생성된다. 공개된 Release의 IPA는 Actions
artifact 보존 기간과 별개로 유지된다. 게시 여부와 링크는 `release` 작업의 요약에서 확인한다.

### 최초 빌드 검증 기록

포크의 Actions를 활성화하고 원격 `main` 그대로
[첫 수동 실행](https://github.com/kinghuijae/Madeira/actions/runs/43581757655)을 시작했다.
이 실행은 Windows 환경 설정 변경이 포함되기 전의 위 기준 커밋을 검증한 것이다.
최종 실행 결과는 이 문서의 아래 검증 기록에 정리한다.

- 로컬 검사: Python 검사 8개, prefix template 검사, 푸시 목적지 10개,
  shell 문법 20개 모두 통과. 카탈로그의 Swift 타입 검사는 macOS에서 별도 수행한다.
- 개인 포크 `origin`으로 `git push --dry-run origin HEAD:main` 성공.
  원격 브랜치에는 변경을 쓰지 않았다.
- 설정 스크립트 재실행 성공. 24개 서브모듈의 push URL 차단 확인.
- 최초 검증 당시 `.github/workflows/build.yml`은 원격 `main`과 동일함을 확인.
- 첫 CI: 2026-11-14에 약 1시간 6분 만에 **전체 성공**.
  `plan`, LLVM, FEX, i386, 런타임 7개, `app` 등 12개 작업이 성공했다.
  첫 실행에 완성된 IPA 캐시가 없으므로 `reuse` 작업 1개만 예상대로 건너뛰었다.
  최종 `Madeira-ipa` artifact 생성까지 확인했으므로 기존 CI는 수정 없이 사용할 수 있다.
- 앱 빌드 도중에도 개인 포크의 캐시 11개(LLVM/FEX/i386/MinGW/런타임)가
  저장된 것을 GitHub API로 확인했다. 캐시 보존 기간·용량·브랜치 접근 규칙에 따라
  이후 실행에서 재사용된다. 이 CI 검증 당시 Windows 환경 설정 변경은 로컬에만 있었다.
- IPA를 `C:\personal_projects\Madeira\dist\Madeira.ipa`에 내려받았다
  (215,160,032바이트). GitHub artifact ZIP의 SHA-256 대조와 프로젝트의
  `runtime-components.py ipa` 검사를 모두 통과했다. 이 검사는 소스 트리,
  구성 요소별 입력 해시, DLL/Mach-O 구조, 필수 파일과 ZIP 무결성을 검사한다.
  SDK 식별자는 같은 CI 실행의 native artifact에서 확인한 값을 사용했다.

```powershell
$env:PYTHONUTF8 = '1'
# 이 IPA를 만든 CI의 SDK 지문. 다른 CI 실행의 IPA에는 해당 실행의 값을 사용한다.
$env:MADEIRA_RUNTIME_SDK = 'f4d1acaa8ca6770ebfa7'
.\.venv\Scripts\python.exe .\tools\build\runtime-components.py ipa .\dist\Madeira.ipa
Remove-Item Env:\MADEIRA_RUNTIME_SDK
```

IPA SHA-256:
`afca22ddf5467f004518ee02ce5374e6ada04507b79a5a7e7cc6b9a52ea47882`.
위 검증 명령은 생성 당시 기준 커밋과 구성 요소 입력이 일치하는 체크아웃에서 사용한다.
Windows 설정이나 문서만 커밋해도 HEAD의 소스 트리가 바뀌므로 기존 IPA와
불일치하는 것이 정상이다. 새 커밋의 IPA는 해당 커밋으로 CI를 실행해 만든다.
IPA는 Git에서 제외했다.

## 스토리 중심 게임을 수정하기 전에

Summer Pockets, 해피라이브쇼업, 오토메도메인의 실제 게임 파일과 iPhone은
이번 환경 검증에서 실행하지 않았다. 에디션과 실행 파일마다 아키텍처·엔진·미디어
의존성이 다를 수 있으므로 각 게임의 원본 EXE부터 확인한다.

```powershell
$env:PYTHONUTF8 = '1'
.\.venv\Scripts\python.exe .\tools\check-game-deps.py 'D:\Games\Example\game.exe'
```

이 도구는 실행 파일을 실행하지 않고 import를 읽는다. `MISSING` 표시는 현재
체크아웃에 있는 DLL과의 비교 결과다. 특히 `i386-windows`는 CI가 생성하므로
빌드 전 32비트 DLL 누락을 곧바로 게임 실행 불가로 판단하지 않는다.
정적 import에 없는 동적 로딩, 코덱, DRM, 영상 재생과 저장 기능은 기기에서 확인한다.

일본어 원본 게임은 먼저 게임별 **Compatibility > Japanese locale**을 확인한다.
현재 구현에는 Shift-JIS/CP932와 Noto Sans JP 설정이 이미 있다.
자세한 내용은 [일본어 게임](JAPANESE.md), [32비트 WoW64](WOW64.md),
[오디오·영상](MEDIA.md), [JIT 설정](JIT.md)을 따른다.
한글 패치판에 일본어 로케일이 맞는지는 해당 패치의 요구사항으로 판단한다.

기기 검증은 타이틀 진입, 글자·줄바꿈, 음성·BGM, 오프닝/영상,
저장·불러오기, 터치/키보드 입력, 장시간 진행 순서로 기록하면 된다.
