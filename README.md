# 弾正戦国転生記

現代人が戦国時代の弱小武将に転生する、歴史IFシミュレーション。

AIが武将・軍師として考え、喋り、動く。  
桶狭間で信長が負けていたら？本能寺の変がなかったら？  
史実という重力に抗いながら、現代の知識だけを武器に乱世を生き抜く。

---

## ⚠️ 現在の公開状況（試験公開版）

本作は現在 **積極的に開発中の試験公開版** です。

| 実装済み | 未実装・今後追加予定 |
|---------|------------------|
| 外交・同盟・従属システム | 領地一括操作 |
| 史実イベント自動発生 | 調略・謀略システム |
| 軍師AI会話 | 援軍要請システム |
| 港湾・塩交易経済 | 食料切れペナルティ |
| 3階層従属（大名→小大名→国人）| 練度・士気の戦闘反映 |
| 大名・小大名・国人の種別表示 | 徴兵コマンド拡充 |

バグ報告・感想は GitHub の Issues へお願いします。  
https://github.com/kyoui-nobushige/danjyo-sengoku-tensei

制作者への連絡先（GitHubアカウントをお持ちでない方）：  
private20060127@gmail.com

---

## 動作環境

- Python 3.10 以上
- Windows 10/11（Mac・Linuxでも動作確認済み）
- ターミナル（コマンドプロンプト / PowerShell）

---

## セットアップ前に：あなたに合ったAIの選び方

このゲームはAI（LLM）が武将・軍師のセリフを生成します。使うAIによって「無料か有料か」「品質」「必要なPC性能」が変わるため、プレイ前に以下から自分に合ったものを選んでください。

**まず、ゲームフォルダ内の `setup.bat` をダブルクリックしてください。** `config.py` の作成（`config.example.py` からのコピー）と、必要なライブラリのインストールが自動で行われます。そのあと、下の表を参考に `config.py` を編集してください。

| あなたの状況 | おすすめ | 手順へのリンク |
|---|---|---|
| GPU（VRAM 8GB以上）を持っている | ① ローカルLLM（LMStudio・完全無料） | [→ ①の手順へ](#local-llm-section) |
| GPUはないが、無料で始めたい | ② Gemini API（無料枠あり） | [→ ②の手順へ](#gemini-section) |
| 品質最優先で、課金しても構わない | ③ Claude API（有料・最高品質） | [→ ③の手順へ](#claude-section) |

迷ったら②（Gemini API）が無料かつ手軽なのでおすすめです。うまくいかない場合は[トラブルシューティング](#troubleshooting-section)もご覧ください。

---

## セットアップ手順

### ステップ1：Pythonをインストールする

Pythonがインストールされていない場合は、以下からダウンロードしてください。

[https://www.python.org/downloads/](https://www.python.org/downloads/)

インストール時に **「Add Python to PATH」にチェックを入れる**ことが重要です。

インストール後、コマンドプロンプトを開いて以下を入力し、バージョンが表示されれば成功です。

```
python --version
```

---

### ステップ2：ゲームファイルを展開する

ダウンロードしたzipファイルを任意のフォルダに展開してください。  
例：`C:\Games\弾正戦国転生記\`

---

### ステップ3：設定ファイルを作成する

ゲームフォルダの中に `config.example.py` というファイルがあります。  
これを **`config.py`という名前でコピー**してください。

**Windowsでのコピー方法：**
1. `config.example.py` を右クリック →「コピー」
2. 同じフォルダ内で右クリック →「貼り付け」
3. 貼り付けたファイルの名前を `config.py` に変更

または、コマンドプロンプトでゲームフォルダに移動して以下を実行：

```
copy config.example.py config.py
```

---

### ステップ4：LLM（AI）を設定する

このゲームはAI（LLM）が武将・軍師の言葉を生成します。  
以下の3つの方法から、自分の環境に合ったものを選んでください。

---

#### <a id="local-llm-section"></a>① ローカルLLM（完全無料・API不要・インターネット接続不要）

自分のPC上でAIを動かす方法です。APIキーもお金も不要です。

**必要なもの：GPU（グラフィックボード）のVRAM 8GB以上推奨**

1. [https://lmstudio.ai](https://lmstudio.ai) を開き、LMStudioをダウンロード・インストールする
2. LMStudioを起動し、上部の検索バーに `gemma-3-12b` と入力してモデルを検索する
   - 推奨：`google/gemma-3-12b`（約8GB・高品質）
   - VRAMが少ない場合：`google/gemma-3-4b`（約4GB・やや品質低下）
3. モデルをダウンロードする（数GBあるので時間がかかります）
4. LMStudioの左メニューから「Local Server」を選び、「Start Server」ボタンを押す
   - ポート番号が `1234` になっていることを確認する
5. `config.py` を開き、以下の行を確認・変更する：
   ```python
   LLM_PROVIDER = "lmstudio"
   ```
6. ゲームを起動すると自動的にLMStudioに接続されます

**注意点：**
- LMStudioのサーバーを起動したままゲームを起動してください
- VRAMが足りない場合、動作が極端に遅くなることがあります
- 日本語の自然さ・キャラクター維持はクラウドAPIより劣ります

---

#### <a id="gemini-section"></a>② Gemini API（無料枠あり・Googleアカウント必要）

GoogleのAIサービスです。無料枠の範囲でプレイできます。

1. [https://aistudio.google.com](https://aistudio.google.com) をブラウザで開く
2. Googleアカウントでログインする
3. 左メニューまたはトップページの「Get API key」をクリックする
4. 「Create API key」ボタンを押してAPIキーを発行する
   - 表示された文字列（`AIzaSy...` で始まる）をコピーしておく
5. `config.py` をテキストエディタ（メモ帳など）で開き、以下の行を編集する：
   ```python
   GEMINI_API_KEY = ""  ← ここにコピーしたAPIキーを貼り付ける
   LLM_PROVIDER = "gemini"
   ```
   例：
   ```python
   GEMINI_API_KEY = "AIzaSyXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
   LLM_PROVIDER = "gemini"
   ```
6. 保存してゲームを起動する

**無料枠について（2025年時点）：**
- 1日あたり一定回数まで無料で利用できます
- プレイスタイルによっては上限に達することがあります
- 上限に達した場合は翌日リセットされます
- 無料枠の条件はGoogleの方針により変更される場合があります

---

#### <a id="claude-section"></a>③ Claude API（有料・最高品質）

AnthropicのAIサービスです。武将のキャラクター・戦国口調・戦略的思考の品質が最も高いです。

1. [https://console.anthropic.com](https://console.anthropic.com) をブラウザで開く
2. アカウントを作成する（クレジットカードの登録が必要です）
3. ログイン後、左メニューの「API Keys」から「Create Key」でAPIキーを発行する
   - 表示された文字列（`sk-ant-...` で始まる）をコピーしておく
   - **このキーは一度しか表示されません。必ずコピーして保存してください**
4. `config.py` をテキストエディタで開き、以下の行を編集する：
   ```python
   ANTHROPIC_API_KEY = ""  ← ここにコピーしたAPIキーを貼り付ける
   LLM_PROVIDER = "anthropic"
   ```
   例：
   ```python
   ANTHROPIC_API_KEY = "sk-ant-XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
   LLM_PROVIDER = "anthropic"
   ```
5. 保存してゲームを起動する

**料金について（重要）：**
- Claude APIは使った分だけ課金されます
- 料金はプレイスタイルによって大きく異なります
  - 軍師との会話を多用する → 多くのトークンを消費
  - AIターンをスキップせず大勢の武将と外交する → 多くのトークンを消費
  - テキストを読むだけで操作が少ない → 比較的少ない消費
- 目安としての金額を示すことは誤解を招くため記載しません
- Anthropicのコンソール画面でいつでも使用量・残高を確認できます
- 予算上限（Budget）を設定することを強く推奨します

---

### ステップ5：ライブラリをインストールする

コマンドプロンプトを開き、ゲームフォルダに移動して以下を実行してください。

```
cd C:\Games\弾正戦国転生記
pip install -r requirements.txt
```

フォルダのパスは実際に展開した場所に合わせてください。

---

### ステップ6：ゲームを起動する

```
python main.py
```

または、ゲームフォルダ内の `start.bat` をダブルクリックしても起動できます。

---

## <a id="troubleshooting-section"></a>トラブルシューティング（よくある質問）

### Q. `pip install` が失敗する

- **原因1：Pythonのバージョンが古い（3.10未満）**
  `python --version` で確認し、3.10未満なら[Python公式サイト](https://www.python.org/downloads/)から最新版を入れ直してください。
- **原因2：pip自体が古い**
  以下を実行してpipを更新してから、再度 `pip install -r requirements.txt` を試してください。
  ```
  python -m pip install --upgrade pip
  ```
- **原因3：ゲームフォルダのパスに問題がある**
  日本語やスペースを含む長いパスで失敗する場合、`C:\Games\danjyo\` のような短い英数字パスに置き直すと解消することがあります。

### Q. `'python' is not recognized as an internal or external command` と表示される

Pythonインストール時に「PATHへの追加」にチェックが入っておらず、Windowsが `python` コマンドの場所を認識できていない状態です。

- **対処法1（推奨）：Pythonを入れ直す**
  [Python公式サイト](https://www.python.org/downloads/)からインストーラーを再実行し、最初の画面で **「Add python.exe to PATH」に必ずチェックを入れて**再インストールしてください。
- **対処法2：PATHを手動で追加する**
  Windowsの「システム環境変数の編集」→「環境変数」→「Path」に、Pythonのインストール先フォルダ（例：`C:\Users\ユーザー名\AppData\Local\Programs\Python\Python312\`）を追加してください。

### Q. ローカルLLM（LMStudio）を選んだのに、ゲームが固まる・エラーになる

LMStudioの「Local Server」が起動していない可能性があります。LMStudio左メニューの「Local Server」で、ポート `1234` のサーバーが起動中（Start Serverを押した状態）になっているか確認してください。ゲームより先にLMStudioのサーバーを起動しておく必要があります。

### Q. Gemini API / Claude APIを選んだのに、エラーになる

`config.py` の `GEMINI_API_KEY` または `ANTHROPIC_API_KEY` が空欄のまま、または `LLM_PROVIDER` の設定と食い違っている可能性があります。以下を確認してください。

- 使いたいAPIに対応するキーが正しく貼り付けられているか（前後に余計な空白・引用符のミスがないか）
- `LLM_PROVIDER` がそのAPIに対応する値（`"gemini"` または `"anthropic"`）になっているか

### Q. `setup.bat` を実行してもうまくいかない

`setup.bat` は内部で `config.example.py` のコピーと `pip install -r requirements.txt` を実行しているだけです。エラーが出た場合は、上記の `pip install` に関する対処法を確認するか、コマンドプロンプトを開いて手動で以下を実行し、表示されるエラーメッセージを確認してください。

```
cd ゲームフォルダのパス
pip install -r requirements.txt
```

---

## APIキーの管理について

`config.py` にはAPIキーが含まれます。  
**このファイルを他人に見せたり、インターネット上に公開しないでください。**  
APIキーが漏洩すると、第三者にあなたのアカウントが不正利用される可能性があります。

---

## ライセンス・著作権

© 2025 姜維信繁. All Rights Reserved.

- 個人利用・プレイ・配信・実況は自由です
- 二次創作・MODは制作者への連絡のうえ歓迎します
- ソースコードの無断転載・商用利用は禁止します

---

## 免責事項

- APIの利用料金はユーザー自身の負担となります
- 料金は各APIサービスの仕様・プレイスタイルにより大きく異なります
- 無料枠の範囲・料金は各APIサービスの規約に準じます
- 本ゲームは歴史的事実をもとにしたフィクションです
