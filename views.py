# coding: utf-8


HEAD = """
<!DOCTYPE html>
<html>
  <head>
    <meta charset="UTF-8">
    <script>
    document.write('<link rel="stylesheet" href="/stylesheets/bootstrap.min.css">');
    document.write('<link rel="stylesheet" href="/stylesheets/bootflat.min.css">');
    document.write('<link rel="stylesheet" href="/stylesheets/isucon-bank.css">');
    </script>
    <title>isucon4</title>
  </head>
  <body>
    <div class="container">
      <h1 id="topbar">
        <a href="/"><script>document.write('<img src="/images/isucon-bank.png" alt="いすこん銀行 オンラインバンキングサービス">');</script></a>
      </h1>
"""


def render_index(error_message):
    pieces = []
    pieces.append(HEAD)
    pieces.append("""
<div id="be-careful-phising" class="panel panel-danger">
  <div class="panel-heading">
    <span class="hikaru-mozi">偽画面にご注意ください！</span>
  </div>
  <div class="panel-body">
    <p>偽のログイン画面を表示しお客様の情報を盗み取ろうとする犯罪が多発しています。</p>
    <p>ログイン直後にダウンロード中や、見知らぬウィンドウが開いた場合、<br>すでにウィルスに感染している場合がございます。即座に取引を中止してください。</p>
    <p>また、残高照会のみなど、必要のない場面で乱数表の入力を求められても、<br>絶対に入力しないでください。</p>
  </div>
</div>

<div class="page-header">
  <h1>ログイン</h1>
</div>
""")

    if error_message:
        pieces.append('<div id="notice-message" class="alert alert-danger" role="alert">')
        pieces.append(error_message)
        pieces.append('</div>')

    pieces.append("""
<div class="container">
  <form class="form-horizontal" role="form" action="/login" method="POST">
    <div class="form-group">
      <label for="input-username" class="col-sm-3 control-label">お客様ご契約ID</label>
      <div class="col-sm-9">
        <input id="input-username" type="text" class="form-control" placeholder="半角英数字" name="login">
      </div>
    </div>
    <div class="form-group">
      <label for="input-password" class="col-sm-3 control-label">パスワード</label>
      <div class="col-sm-9">
        <input type="password" class="form-control" id="input-password" name="password" placeholder="半角英数字・記号（２文字以上）">
      </div>
    </div>
    <div class="form-group">
      <div class="col-sm-offset-3 col-sm-9">
        <button type="submit" class="btn btn-primary btn-lg btn-block">ログイン</button>
      </div>
    </div>
  </form>
</div>

    </div>

  </body>
</html>
""")
    return ''.join(pieces)


def render_mypage(session):
    return ''.join([HEAD, """
<div class="alert alert-success" role="alert">
  ログインに成功しました。<br>
  未読のお知らせが０件、残っています。
</div>

<dl class="dl-horizontal">
  <dt>前回ログイン</dt>
  <dd id="last-logined-at">""", str(session['last_login_at']), """</dd>
  <dt>最終ログインIPアドレス</dt>
  <dd id="last-logined-ip">""", str(session['last_login_ip']), """</dd>
</dl>

<div class="panel panel-default">
  <div class="panel-heading">
    お客様ご契約ID：""", session['login'].encode('utf-8'), """ 様の代表口座
  </div>
  <div class="panel-body">
    <div class="row">
      <div class="col-sm-4">
        普通預金<br>
        <small>東京支店　1111111111</small><br>
      </div>
      <div class="col-sm-4">
        <p id="zandaka" class="text-right">
          ―――円
        </p>
      </div>

      <div class="col-sm-4">
        <p>
          <a class="btn btn-success btn-block">入出金明細を表示</a>
          <a class="btn btn-default btn-block">振込・振替はこちらから</a>
        </p>
      </div>

      <div class="col-sm-12">
        <a class="btn btn-link btn-block">定期預金・住宅ローンのお申込みはこちら</a>
      </div>
    </div>
  </div>
</div>
    </div>

  </body>
</html>
"""])
