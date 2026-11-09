# MTG Deck Viewer

デッキリストを読み込み、カード画像をブラウザーで一覧表示するローカルアプリです。カード情報と画像は Scryfall API から取得します。インターネット接続が必要です。

## Windowsアプリ版

`dist\MTGDeckViewerHTML.exe` をダブルクリックすると、ブラウザー版と同じHTML画面が独立したウィンドウに表示されます。Pythonは不要ですが、Microsoft Edge WebView2 Runtimeとインターネット接続が必要です。カードのリンクは既定のブラウザーで開き、PNG保存では保存先を選択できます。ウィンドウを閉じると専用のローカルサーバーも終了します。

Windows上でEXEを再作成する場合は、プロジェクトフォルダから以下を実行します。

```powershell
python -m pip install -r .\requirements-build.txt
.\src\build_web_window.bat
```

Pythonから起動する場合は `python -m pip install -r .\requirements-web-window.txt` を実行し、`src\start_web_window.bat` を使用してください。

## ブラウザー版の起動方法

Windows では `src\start_deck_viewer.bat` をダブルクリックしてください。Python 3 がインストールされていれば、ローカル画面がブラウザーで開きます。終了するには起動したコマンド画面で `Ctrl+C` を押します。

PowerShell から起動する場合（プロジェクトフォルダから）：

```powershell
Set-Location .\src
python -m mtg.mtg_deck_viewer
```

## フォルダ構成とテスト

- `src/mtg/`: アプリ本体、カード検索、HTML表示用ウィンドウのPythonコード
- `src/tests/`: 自動テスト
- `src/start_web_window.bat`、`src/start_deck_viewer.bat`: 起動用バッチ
- `src/build_web_window.bat`: WindowsアプリのEXEビルド
- `dist/MTGDeckViewerHTML.exe`: Windows HTML版の実行ファイル
- `mtg_deck_viewer.html`: ブラウザー版の画面

プロジェクトフォルダで `python -m unittest discover -s src -v` を実行すると、ブラウザー版とWindowsアプリ版のテストを実行します。
カード検索CLIは `src` フォルダで `python -m mtg.mtg_card_search --help` を実行すると使い方を確認できます。

## デッキリスト

テキストを貼り付けるか、`.txt` ファイルを選択します。1行に1種類を記述してください。

```text
4 Lightning Bolt
2 Island

Sideboard
2 Negate
```

`4 Card Name`、`4x Card Name`、枚数を省略した `Card Name` に対応します。同じカードはメインボード／サイドボードごとにまとめて表示します。セット情報を含む `Card Name (SET) 123` 形式では、セットとコレクター番号を使って印刷版を検索します。

MTGアリーナ（MTGA）でエクスポートしたデッキリストも貼り付けられます。
`Deck`、`Sideboard`、`Commander`、`Companion` の各見出しを区別して表示します。
日本語の `デッキ`、`サイドボード`、`統率者`、`相棒` も使用できます。
`About` セクションのデッキ名などはカードとして扱いません。
カード名が日本語の場合も、セットコードとコレクター番号が付いていれば検索できます。
画像とカード名はScryfallから取得したものです。指定したセットと番号が見つからない場合はカード名で再検索します。その場合、別の印刷版やデジタル版以外の画像になることがあります。カード名でも見つからない場合はエラーを表示します。
カード画像をクリックすると、取得した印刷版のScryfallページを新しいタブで開きます。画像のないカードはカード名から開けます。Scryfallのリンクを取得できなかった場合はカードにその旨を表示します。
「デッキリストをクリア」は入力欄を消去します。表示中の検索結果は残ります。「検索結果をPNGで保存」は、各区分・タイプの見出しと枚数を含む一覧画像を保存します。ブラウザー版では保存時にカード画像を再読み込みします。画像が取得できない場合や結果が大きすぎる場合はエラーを表示します。
画面とPNGではカード画像と枚数を表示します。画像がないカードや検索できなかったカードは、名前とエラーを表示します。
検索結果は各区分内でタイプごとに見出しを付け、プレインズウォーカー、クリーチャー、ソーサリー、インスタント、アーティファクト、エンチャント、土地の順に表示します。見出しの枚数はデッキ内の合計枚数です。複数のタイプや面を持つカードは、土地を含む場合は土地、土地を含まずクリーチャーを含む場合はクリーチャーに分類します。それ以外は上記の順で最も早いタイプに分類します。その他のタイプは土地の後、タイプを取得できないカードは末尾に表示します。同じ分類のカードは入力順です。

検索には Scryfall の公開APIを利用しています。取得したカード画像を表示する際は Scryfall API の利用条件に従ってください。
カード名は最大75種類ずつまとめて取得します。Scryfallの検索制限が表示された場合は、案内された時間を置いてから再試行してください。
