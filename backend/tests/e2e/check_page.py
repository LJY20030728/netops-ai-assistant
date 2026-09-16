# -*- coding: utf-8 -*-
"""检查服务实际返回的页面是否包含 sources 处理逻辑（临时）。"""
import urllib.request

html = urllib.request.urlopen("http://127.0.0.1:8000/", timeout=10).read().decode("utf-8")
print("served page len:", len(html))
print("has addSourcesFooter:", "addSourcesFooter" in html)
print("has 参考来源:", "参考来源" in html)
print("has sources handler:", "data.type === 'sources'" in html)
