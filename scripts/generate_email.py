import os
import pandas as pd
import base64
from datetime import date
from pathlib import Path

def generate_email_content():
    # 确保charts目录存在
    charts_dir = Path("charts")
    charts_dir.mkdir(exist_ok=True)
    
    # 读取所有CSV文件并转换为HTML表格
    tables_html = ''
    for csv_file in Path('.').glob('*.csv'):
        df = pd.read_csv(csv_file)
        tables_html += f'<h2>{csv_file.stem}</h2>'
        tables_html += df.to_html(index=False, border=1)
        tables_html += '<br><br>'
    
    # 嵌入所有图片
    images_html = ''
    for img_file in charts_dir.glob('*.png'):
        with open(img_file, 'rb') as img:
            img_data = base64.b64encode(img.read()).decode()
            images_html += f'<h2>{img_file.stem}</h2>'
            images_html += f'<img src="data:image/png;base64,{img_data}" /><br><br>'

    if len(images_html) == 0 and len(tables_html) == 0:
        return f'''<html>
<body>
  <h1>今日推荐股票 - {today}</h1>
  <p>股市有风险，投资需谨慎<p>
  <h2>保持观望</h2>
</body>
</html>'''
    
    # 生成完整的HTML邮件内容
    today = date.today().strftime('%Y-%m-%d')
    return f'''<html>
<body>
  <h1>今日推荐股票 - {today}</h1>
  <p>股市有风险，投资需谨慎<p>
  <h2>数据表格</h2>
  {tables_html}
  <h2>图表</h2>
  {images_html}
</body>
</html>'''

if __name__ == "__main__":
    content = generate_email_content()
    with open('email_content.html', 'w') as f:
        f.write(content)
    print("邮件内容已生成到 email_content.html")