from cartero.llm import generate_changelog

diff = """
diff --git a/cartero/llm.py b/cartero/llm.py
index 1234567..abcdefg 100644
--- a/cartero/llm.py
+++ b/cartero/llm.py
@@ -1,3 +1,10 @@
+def generate_changelog(diff_text, config=None, *, context_recap=None):
+    ...
"""

result = generate_changelog(diff)
print(result)
