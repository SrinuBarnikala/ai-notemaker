import re

with open("frontend/index.html", encoding="utf-8") as f:
    text = f.read()

modal_ids = re.findall(r'id=["\']([^"\']*(?:modal|drawer|dialog|overlay)[^"\']*)["\']', text)
print("Modals/Drawers found:", sorted(list(set(modal_ids))))
