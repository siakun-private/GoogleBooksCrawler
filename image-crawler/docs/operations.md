# 이미지 수집 운영 안내

설치는 [README](../README.md)의 명령을 사용합니다. `run_gui.bat` 또는 이 폴더에서 `python gui_app.py`로 GUI를 시작합니다.

## GUI 흐름

Scraper에서 다운로드 폴더와 책 URL을 정하고 `Initialize Driver`로 Chrome을 엽니다. `Navigate to Book`으로 이동해 필요한 로그인은 브라우저에서 진행합니다. 본문이 표시되면 `Start Scraping`을 누릅니다. 수집 루프에 책의 끝을 확정하는 검사가 없으므로 필요한 범위가 저장됐는지 확인하고 `Stop Scraping`, `Close Driver` 순서로 끝냅니다.

다운로드 시작 번호는 출력 폴더의 기존 파일과 겹치지 않게 정합니다. 화면의 수집 개수는 브라우저 다운로드 완료 수를 증명하지 않습니다. 내려받는 중인 파일이 남지 않았는지, 이미지가 정상적으로 열리는지 별도로 확인합니다.

PNG Converter는 확장자가 PNG인 파일도 실제 이미지 형식을 확인해 저장합니다. JPEG 변환은 RGB 변환과 선택적인 선명도 보정을 수행합니다. File Reorder는 미리보기를 본 뒤 임시 복사본에서 번호를 확인합니다. PDF Creator는 지정 폴더의 PNG를 숫자 순으로 모으며 JPEG 변환 결과를 자동으로 입력받는 파이프라인이 아닙니다.

색상 및 선명도 보정은 시각적인 선택입니다. 보정을 해도 원본에 없는 세부 정보가 복원되지는 않습니다. 손실 없는 보관이 목적이면 원본 다운로드와 변환 결과를 다른 폴더에 둡니다.

## 노트북 실행

노트북이 필요한 경우 같은 가상환경에 Jupyter를 설치하고 이 폴더에서 엽니다.

```powershell
.\.venv\Scripts\python.exe -m pip install jupyter
.\.venv\Scripts\python.exe -m jupyter notebook
```

수집은 `Source/book.ipynb`, PNG/JPEG 처리는 `Source/book_to_png.ipynb`, 번호 정리는 `Source/reorder.ipynb`, PDF 생성은 `Source/png_to_pdf.ipynb`에서 읽습니다. 실행 전에 셀의 책 URL, `download_path`, `directory_path`, `force_startnum`과 작업 디렉터리를 확인합니다. Jupyter가 노트북 폴더를 기준으로 실행하면 상대 경로의 의미가 GUI와 달라집니다.

`Source/test_*.ipynb`는 브라우저 조작 실험입니다. 자동 테스트 명령에 포함하지 않습니다. 무한 수집 셀은 실행을 중단해야 종료됩니다.

## 문제 확인

Chrome 초기화 실패는 현재 Chrome과 드라이버의 조합, 사용하는 Python 환경, 같은 프로필을 점유한 Chrome을 먼저 확인합니다. 저장소의 구형 `Scripts/python.exe`를 새 환경으로 오인하지 않습니다. 버전을 변경해야 하면 원래 설치 버전을 기록하고 실제 수집 화면으로 호환성을 확인합니다.

이미지가 내려오지 않으면 다운로드 권한과 경로를 확인하고 실제 iframe 및 페이지 이미지 DOM이 `modules/scraper.py`의 선택자와 일치하는지 봅니다. 본문이 HTML로 흐르는 리더라면 이 구현의 이미지 선택자가 맞지 않을 수 있으며 [EPUB Crawler](../../epub-crawler/README.md)가 해당 경로입니다.

PDF가 누락된 페이지로 만들어졌다면 입력 PNG 목록과 이미지 열기 오류를 확인합니다. 현재 변환기는 개별 파일 오류를 출력하고 다음 파일을 계속 처리하므로 PDF 생성 성공만으로 입력 전체가 포함됐다고 판단하지 않습니다.
