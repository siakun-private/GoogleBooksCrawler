# 검증 절차

검사는 이 폴더에서 실행합니다. 원본의 글자 수와 자산 보존, EPUB 규격, 브라우저 표시를 서로 다른 근거로 확인합니다. 출력 파일이 만들어졌다는 사실만으로 세 항목을 모두 통과했다고 보고하지 않습니다.

## 코드와 저장된 자료

```powershell
python -X utf8 -m unittest -v test_export.py
python -m py_compile browser.py extract.py build_epub.py html_reader.py
node --check reader/reader.js
```

Node.js는 JavaScript 구문 검사에만 사용하며 HTML 실행이나 추출의 필수 환경은 아닙니다. Python 회귀 검사는 누락 이미지, 끊어진 각주, 외부 CSS 의존성, 콘텐츠 밖 경로를 거부하는지 확인합니다. HTML 직렬화와 JSON 삽입 경계도 검사합니다.

저장된 자료만 검사할 때는 패키저의 검증 함수를 사용합니다. 이 명령은 책을 다시 내려받지 않으며 EPUB 파일도 덮어쓰지 않습니다.

```powershell
python -X utf8 -c "from pathlib import Path; from build_epub import validate_content; validate_content(Path('output/content/book.json')); print('Local content OK')"
```

추출 결과는 `capture-report.json`의 누락 앵커, 원본 글자 수와 자산 기록으로 확인합니다. `source_chars`와 저장한 텍스트는 UTF-16 단위로 비교합니다. ZIP 안에 로컬 자산이 포함됐는지는 패키저가 검사하고 각 자산의 내용은 해시로 비교합니다.

## EPUBCheck

EPUBCheck JAR와 Java가 설치돼 있으면 환경 변수에 실제 JAR 경로를 지정한 뒤 실행합니다. 저장소의 로컬 도구 폴더에 검사기가 보관돼 있으면 아래 기본 경로를 사용할 수 있습니다. EPUB 경로는 책 메타데이터의 제목을 그대로 추측하지 말고 출력 파일을 선택합니다.

```powershell
$epubFile = Get-ChildItem -LiteralPath output -Filter '*.epub' | Select-Object -First 1
if (-not $epubFile) { throw 'EPUB 파일이 없습니다.' }
if (-not $env:EPUBCHECK_JAR) { $env:EPUBCHECK_JAR = Join-Path (Get-Location) '../.local/tools/epubcheck/epubcheck.jar' }
if (-not $env:EPUBCHECK_JAR -or -not (Test-Path -LiteralPath $env:EPUBCHECK_JAR)) { throw 'EPUBCHECK_JAR에 설치된 JAR 경로를 지정해 주세요.' }
java '-Dfile.encoding=UTF-8' -jar $env:EPUBCHECK_JAR $epubFile.FullName --json output/epubcheck-report.json
```

책이 여러 개면 첫 파일 선택 명령 대신 확인할 EPUB 경로를 직접 지정합니다. fatal, error, warning과 검사기 버전을 JSON에서 읽습니다. 파일을 다시 생성한 뒤에는 예전 검사 보고서를 새 파일의 결과로 사용하지 않습니다.

## 로컬 HTML 브라우저 검사

```powershell
python -X utf8 html_reader.py output/content/book.json
```

생성한 `output/content/index.html`을 Orca 탭 하나에 엽니다. 같은 로컬 책을 여러 탭에 열었으면 하나로 정리합니다. 다음 명령은 실제 탭에서 원본 페이지와 목차 목표를 순회하고 현재 브라우저의 프록시를 새로 찾습니다.

```powershell
python -X utf8 tools/verify_reader.py output/content/book.json
```

검사기는 원본과 HTML 직렬화의 텍스트 및 앵커, 이미지 로딩, 페이지 범위와 이동 목표의 화면 좌표, 외부 의존성을 확인합니다. 상태를 저장했다가 검사 후 복원하며 캐시를 무시하고 새 HTML을 읽습니다. 결과는 출력 폴더의 `reader-verification.latest.json`에 씁니다. 오류가 있으면 비정상 종료합니다.

기능이나 스타일을 바꿨다면 이 검사와 함께 밝은/어두운 테마, 글꼴 변경, 행 간격, 정렬, 한/두 페이지, 북마크 추가/삭제 및 새로고침 복원, 검색, 각주 왕복을 직접 확인합니다. 좁은 화면에서는 패널과 하단 페이지 범위가 창 안에 들어오는지 봅니다. 자동 좌표 검사는 색상, 가독성과 그림의 선명도까지 보장하지 않습니다.

## 변경 범위에 맞는 마무리

UI만 바뀌면 HTML을 다시 만들고 브라우저를 검사합니다. EPUB 패키징이 바뀌면 회귀 검사와 규격 검사를 수행합니다. 추출 로직이 바뀌면 대상 리더에서 완전한 구간과 자산을 다시 비교합니다. 기존 출력 전체를 지워 다시 수집하는 것을 기본 검사로 삼지 않습니다.
