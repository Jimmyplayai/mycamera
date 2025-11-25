#!/usr/bin/env python
import urllib.request
import os

# 尝试多个CDN源
cdn_urls = [
    'https://unpkg.com/chart.js@4.4.0/dist/chart.umd.min.js',
    'https://lib.baomitu.com/Chart.js/4.4.0/chart.umd.min.js',
    'http://cdn.bootcdn.net/ajax/libs/Chart.js/4.4.0/chart.umd.min.js',
]

static_dir = '/workspace/blip2_nllb_data/mycamera/static/js'
os.makedirs(static_dir, exist_ok=True)

output_file = os.path.join(static_dir, 'chart.min.js')

for url in cdn_urls:
    try:
        print(f'Trying to download from: {url}')
        urllib.request.urlretrieve(url, output_file)
        file_size = os.path.getsize(output_file)
        print(f'✓ Successfully downloaded! File size: {file_size} bytes')
        if file_size > 10000:  # 至少10KB，确保不是错误页面
            print(f'✓ File saved to: {output_file}')
            break
    except Exception as e:
        print(f'✗ Failed: {e}')
        continue
else:
    print('All CDN sources failed!')
