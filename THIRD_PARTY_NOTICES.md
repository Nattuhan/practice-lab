# Third-party software notices

PracticeLabはMITライセンスで公開しますが、配布物には各プロジェクト固有のライセンスが適用される
第三者ソフトウェアを含みます。主なものは次のとおりです。

| ソフトウェア | 用途 | ライセンス情報 |
|---|---|---|
| Electron | デスクトップアプリ基盤 | [MIT](https://github.com/electron/electron/blob/main/LICENSE) |
| FFmpeg / FFprobe | 音声・動画変換 | [FFmpeg Legal](https://ffmpeg.org/legal.html) |
| Node.js | yt-dlpのJavaScript実行環境 | [Node.js licenses](https://github.com/nodejs/node/blob/main/LICENSE) |
| FastAPI / Uvicorn | ローカルAPI | 各プロジェクトの配布ライセンス |
| yt-dlp | 動画取得 | [Unlicense](https://github.com/yt-dlp/yt-dlp/blob/master/LICENSE) |
| PyTorch | 解析実行 | [BSD-style](https://github.com/pytorch/pytorch/blob/main/LICENSE) |
| NATTEN | 音楽構成解析依存 | [BSD 3-Clause](https://github.com/SHI-Labs/NATTEN/blob/main/LICENSE) |
| all-in-one-fix | 音楽構成解析 | 配布パッケージのライセンス |
| Demucs | パート分離 | [MIT](https://github.com/facebookresearch/demucs/blob/main/LICENSE) |
| WaveSurfer.js / Lucide | UI | 各プロジェクトの配布ライセンス |

正式リリースにはNodeのCycloneDX SBOMとPython依存関係一覧を添付します。依存パッケージの完全な
一覧とバージョンは、各リリースの`*sbom*.json`および`*dependencies*.json`を参照してください。

利用者が解析する音源・動画・楽譜などの権利は、それぞれの権利者に帰属します。PracticeLabの
ライセンスは、それら第三者コンテンツの利用許諾を与えるものではありません。
