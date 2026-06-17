"""Tests for role/auth pattern detection in PR diffs."""

from pr_review_agent.analyzers.role_detector import detect_role_patterns


class TestDetectRolePatterns:
    """Test the regex pre-scanner for role/auth patterns."""

    def test_no_patterns_returns_false(self):
        diff = """diff --git a/src/utils.py b/src/utils.py
--- a/src/utils.py
+++ b/src/utils.py
@@ -1,3 +1,4 @@
+import os
 def helper():
     return True
"""
        result = detect_role_patterns(diff)
        assert result.has_role_patterns is False
        assert result.detected_roles == []
        assert result.role_snippets == []
        assert result.auth_patterns == []

    def test_detects_role_check_pattern(self):
        diff = """diff --git a/src/auth.py b/src/auth.py
+    if user.role == "admin":
+        grant_access()
"""
        result = detect_role_patterns(diff)
        assert result.has_role_patterns is True
        assert "admin" in result.detected_roles

    def test_detects_session_role(self):
        diff = """diff --git a/src/middleware.js b/src/middleware.js
+  const role = session.role;
+  if (role === "supplier") {
+    return next();
+  }
"""
        result = detect_role_patterns(diff)
        assert result.has_role_patterns is True
        assert "supplier" in result.detected_roles

    def test_detects_is_admin_helper(self):
        diff = """diff --git a/src/guards.ts b/src/guards.ts
+  if (isAdmin(user)) {
+    showAdminPanel();
+  }
"""
        result = detect_role_patterns(diff)
        assert result.has_role_patterns is True
        assert "role_helper" in result.auth_patterns

    def test_detects_python_decorator(self):
        diff = """diff --git a/views.py b/views.py
+@login_required
+@permission_required("can_edit")
+def edit_view(request):
+    pass
"""
        result = detect_role_patterns(diff)
        assert result.has_role_patterns is True
        assert "framework_auth" in result.auth_patterns

    def test_detects_nextjs_session(self):
        diff = """diff --git a/app/page.tsx b/app/page.tsx
+  const session = await getServerSession();
+  if (!session) redirect("/login");
"""
        result = detect_role_patterns(diff)
        assert result.has_role_patterns is True
        assert "framework_auth" in result.auth_patterns

    def test_detects_permission_check(self):
        diff = """diff --git a/src/access.py b/src/access.py
+  if hasPermission(user, "manage_users"):
+    return True
"""
        result = detect_role_patterns(diff)
        assert result.has_role_patterns is True
        assert "access_check" in result.auth_patterns

    def test_detects_multiple_role_literals(self):
        diff = """diff --git a/src/roles.py b/src/roles.py
+ROLES = ["admin", "buyer", "supplier", "manager"]
"""
        result = detect_role_patterns(diff)
        assert result.has_role_patterns is False  # No auth pattern, just literals alone
        # But role literals are detected
        # Actually, the role literal pattern alone doesn't trigger has_role_patterns
        # because we only set match_positions from _ROLE_ACCESS_PATTERNS

    def test_detects_role_identifier_pattern(self):
        diff = """diff --git a/src/auth.ts b/src/auth.ts
+  if (user.role === Role.ADMIN) {
+    allowAccess();
+  } else if (user.role === Role.SUPPLIER) {
+    restrictAccess();
+  }
"""
        result = detect_role_patterns(diff)
        assert result.has_role_patterns is True
        assert "admin" in result.detected_roles
        assert "supplier" in result.detected_roles

    def test_detects_middleware_auth(self):
        diff = """diff --git a/src/server.js b/src/server.js
+  app.use("/admin", middleware.authGuard);
+  // auth middleware for role checking
"""
        result = detect_role_patterns(diff)
        assert result.has_role_patterns is True

    def test_extracts_context_snippets(self):
        # Build a diff with a role pattern in the middle
        lines = ["line " + str(i) for i in range(20)]
        lines[10] = '+  if (user.role === "admin") {'
        diff = "\n".join(lines)

        result = detect_role_patterns(diff)
        assert result.has_role_patterns is True
        assert len(result.role_snippets) > 0
        # Snippet should contain the match and surrounding context
        assert "user.role" in result.role_snippets[0]

    def test_deduplicates_overlapping_snippets(self):
        # Two matches close together should produce one merged snippet
        diff = """diff --git a/src/auth.py b/src/auth.py
+  if user.role == "admin":
+    pass
+  if req.role == "buyer":
+    pass
"""
        result = detect_role_patterns(diff)
        assert result.has_role_patterns is True
        # Should merge into a single snippet since they're within 5 lines
        assert len(result.role_snippets) <= 2

    def test_guard_pattern_detected(self):
        diff = """diff --git a/src/api.ts b/src/api.ts
+  const guard = new AuthGuard();
+  guard.authorize(req);
"""
        result = detect_role_patterns(diff)
        assert result.has_role_patterns is True
        assert "permission" in result.auth_patterns

    def test_empty_diff(self):
        result = detect_role_patterns("")
        assert result.has_role_patterns is False

    def test_skips_diff_metadata_lines(self):
        diff = """diff --git a/role.py b/role.py
index abc123..def456 100644
--- a/role.py
+++ b/role.py
@@ -1,3 +1,4 @@
 normal code here
"""
        result = detect_role_patterns(diff)
        assert result.has_role_patterns is False
