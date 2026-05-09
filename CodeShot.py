import sublime
import sublime_plugin

import html
import os
import re
import shutil
import subprocess
import tempfile
import time
import webbrowser
from datetime import datetime


DEFAULT_THEME = "vscode-dark"


def hidden_startupinfo():
    """Return STARTUPINFO to hide child process windows on Windows."""
    if os.name != "nt":
        return None

    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    return startupinfo


def delete_file_quietly(path):
    """Best-effort file deletion."""
    if not path:
        return

    try:
        if os.path.exists(path):
            os.remove(path)
    except OSError:
        pass


def delete_file_later(path, delay=60000):
    """Delete a temporary file after a short delay, useful for preview files."""
    def cleanup():
        delete_file_quietly(path)

    sublime.set_timeout_async(cleanup, delay)



class CodeShotSetThemeCommand(sublime_plugin.WindowCommand):
    def run(self, theme=DEFAULT_THEME):
        settings = sublime.load_settings("CodeShot.sublime-settings")
        settings.set("theme", theme)
        sublime.save_settings("CodeShot.sublime-settings")

    def is_checked(self, theme=DEFAULT_THEME):
        settings = sublime.load_settings("CodeShot.sublime-settings")
        current_theme = settings.get("theme", DEFAULT_THEME)
        return current_theme == theme


class CodeShotCommand(sublime_plugin.TextCommand):
    def run(self, edit, mode="copy"):
        settings = sublime.load_settings("CodeShot.sublime-settings")
        config = self.load_config(settings)

        code = self.get_selected_text(self.view, config.get("dedent_selection", True))

        if not code.strip():
            sublime.message_dialog("Please select some code first.")
            return

        language = self.detect_language(self.view, config["language_override"])

        html_content = self.build_html(code, language, config)
        html_path = self.write_temp_file("codeshot.html", html_content)

        if mode == "preview":
            webbrowser.open("file:///" + html_path.replace("\\", "/"))
            delete_file_later(html_path)
            return

        browser_path = self.find_browser(config["chrome_path"])
        if not browser_path:
            delete_file_quietly(html_path)
            sublime.message_dialog(
                "Chrome or Edge was not found.\n\n"
                "Set chrome_path in CodeShot.sublime-settings."
            )
            return

        capture_height = self.get_capture_height(code, config)
        save_to_desktop = (mode == "save")
        png_path = self.get_output_png_path(save_to_desktop)

        try:
            ok, message = self.render_png(
                browser_path,
                html_path,
                png_path,
                self.get_capture_width(code, config),
                capture_height
            )

            if not ok:
                sublime.message_dialog("PNG export failed.\n\n" + message)
                return

            if mode == "copy":
                copied, clip_error = self.copy_png_to_clipboard(png_path)
                if not copied:
                    sublime.message_dialog(
                        "PNG was created but clipboard copy failed.\n\n"
                        "Temporary PNG:\n{}\n\nError:\n{}".format(png_path, clip_error)
                    )
                    return

                sublime.message_dialog("CodeShot Saved to Clipboard Successfully.")
                return

            if mode == "save":
                sublime.message_dialog("CodeShot Saved to Desktop Successfully.")
                return

        finally:
            delete_file_quietly(html_path)
            if mode == "copy":
                delete_file_quietly(png_path)

    def load_config(self, settings):
        return {
            "title": settings.get("title", "Code Snapshot"),
            "theme": settings.get("theme", DEFAULT_THEME),
            "font_size": int(settings.get("font_size", 15)),
            "font_family": settings.get("font_family", "Consolas, 'Courier New', monospace"),
            "show_window_buttons": bool(settings.get("show_window_buttons", True)),
            "show_line_numbers": bool(settings.get("show_line_numbers", True)),
            "padding": int(settings.get("padding", 32)),
            "page_padding": int(settings.get("page_padding", 10)),
            "auto_trim_width": bool(settings.get("auto_trim_width", True)),
            "min_capture_width": int(settings.get("min_capture_width", 700)),
            "max_capture_width": int(settings.get("max_capture_width", 2200)),
            "fixed_capture_width": int(settings.get("fixed_capture_width", 1400)),
            "border_radius": int(settings.get("border_radius", 22)),
            "card_max_width": int(settings.get("card_max_width", 1180)),
            "shadow_blur": int(settings.get("shadow_blur", 90)),
            "shadow_spread": int(settings.get("shadow_spread", 30)),
            "shadow_alpha": float(settings.get("shadow_alpha", 0.35)),
            "screenshot_width": int(settings.get("screenshot_width", 1400)),
            "save_to_desktop": bool(settings.get("save_to_desktop", True)),
            "chrome_path": settings.get("chrome_path", ""),
            "language_override": settings.get("language_override", ""),
            "show_footer": bool(settings.get("show_footer", True)),
            "footer_text": settings.get("footer_text", "CodeShot by Yasin Jagral"),
            "auto_trim_height": bool(settings.get("auto_trim_height", True)),
            "min_capture_height": int(settings.get("min_capture_height", 240)),
            "max_capture_height": int(settings.get("max_capture_height", 8000)),
            "fixed_capture_height": int(settings.get("fixed_capture_height", 900)),
            "page_background": settings.get("page_background", "#ffffff"),
            "capture_balance_buffer": int(settings.get("capture_balance_buffer", 18)),
            "dedent_selection": bool(settings.get("dedent_selection", True)),
            "wrap_long_lines": bool(settings.get("wrap_long_lines", True))
        }

    def get_selected_text(self, view, dedent_selection=True):
        parts = []
        for region in view.sel():
            if not region.empty():
                parts.append(view.substr(region))

        text = "\n".join(parts)
        if not text or not dedent_selection:
            return text

        lines = text.split("\n")
        non_empty = [line for line in lines if line.strip()]
        if not non_empty:
            return text

        def leading_count(line):
            count = 0
            for ch in line:
                if ch == ' ':
                    count += 1
                elif ch == '	':
                    count += 4
                else:
                    break
            return count

        min_indent = min(leading_count(line) for line in non_empty)
        if min_indent <= 0:
            return text

        dedented = []
        for line in lines:
            remaining = min_indent
            i = 0
            while i < len(line) and remaining > 0:
                if line[i] == ' ':
                    remaining -= 1
                    i += 1
                elif line[i] == '	':
                    remaining -= 4
                    i += 1
                else:
                    break
            dedented.append(line[i:])

        return "\n".join(dedented)

    def detect_language(self, view, override_value):
        if override_value:
            return override_value.lower().strip()

        syntax = (view.settings().get("syntax") or "").lower()

        if "html" in syntax or "xml" in syntax:
            return "html"
        if "css" in syntax or "scss" in syntax or "sass" in syntax or "less" in syntax:
            return "css"
        if "javascript" in syntax or "typescript" in syntax or "jsx" in syntax or "tsx" in syntax:
            return "javascript"
        if "python" in syntax:
            return "python"
        if "c#" in syntax or "csharp" in syntax:
            return "csharp"
        if "sql" in syntax:
            return "sql"
        if "json" in syntax:
            return "json"
        if "php" in syntax:
            return "php"
        if "java" in syntax:
            return "java"
        if "c++" in syntax or "cpp" in syntax:
            return "cpp"
        if "shell" in syntax or "bash" in syntax:
            return "bash"
        if "visual basic" in syntax or "vb" in syntax:
            return "vb"

        return "plain"

    def get_language_label(self, language):
        labels = {
            "html": "HTML",
            "xml": "XML",
            "css": "CSS",
            "javascript": "JavaScript",
            "typescript": "TypeScript",
            "python": "Python",
            "csharp": "C#",
            "sql": "SQL",
            "json": "JSON",
            "php": "PHP",
            "java": "Java",
            "cpp": "C++",
            "bash": "Bash",
            "vb": "VB",
            "plain": "Plain Text"
        }
        return labels.get(language, language.upper() if language else "Plain Text")

    def get_capture_height(self, code, config):
        if not config["auto_trim_height"]:
            return config["fixed_capture_height"]

        lines = code.split("\n")
        line_count = max(1, len(lines))

        base_chars = 84 if config.get("wrap_long_lines", True) else 1000000
        visual_lines = 0
        for line in lines:
            expanded = line.expandtabs(4)
            length = len(expanded)
            if config.get("wrap_long_lines", True):
                wraps = max(1, (length + base_chars - 1) // base_chars)
            else:
                wraps = 1
            visual_lines += wraps

        line_height = config["font_size"] * 1.95
        top_bar_height = 60
        footer_height = 44 if config["show_footer"] else 0
        code_padding = config["padding"] * 2
        page_padding = config["page_padding"] * 2
        safety_buffer = 160

        estimated = int(
            top_bar_height
            + footer_height
            + code_padding
            + page_padding
            + (visual_lines * line_height)
            + safety_buffer
        )

        estimated = max(config["min_capture_height"], estimated)
        estimated = min(config["max_capture_height"], estimated)

        return estimated

    def get_capture_width(self, code, config):
        if not config["auto_trim_width"]:
            return config["fixed_capture_width"]

        lines = code.split("\n")
        expanded_lines = [line.expandtabs(4) for line in lines] if lines else [""]
        max_chars = max(len(line) for line in expanded_lines)

        if config.get("wrap_long_lines", True):
            # Keep the card width reasonable and let long lines wrap.
            target_chars = min(max_chars, 84)
            char_width = config["font_size"] * 0.74
            line_number_width = 92 if config["show_line_numbers"] else 0
            card_padding = config["padding"] * 2
            page_padding = config["page_padding"] * 2
            safety_buffer = 140
            estimated = int(
                (target_chars * char_width)
                + line_number_width
                + card_padding
                + page_padding
                + safety_buffer
            )
        else:
            char_width = config["font_size"] * 0.78
            line_number_width = 90 if config["show_line_numbers"] else 0
            card_padding = config["padding"] * 2
            page_padding = config["page_padding"] * 2
            safety_buffer = 180
            estimated = int(
                (max_chars * char_width)
                + line_number_width
                + card_padding
                + page_padding
                + safety_buffer
            )

        estimated = max(config["min_capture_width"], estimated)
        estimated = min(config["max_capture_width"], estimated)
        return estimated

    def build_html(self, code, language, config):
        theme = self.get_theme(config["theme"])
        code_html = self.render_code(code, language, config["show_line_numbers"])
        header_title = "{} • {}".format(config["title"], self.get_language_label(language))

        buttons_html = ""
        if config["show_window_buttons"]:
            buttons_html = (
                '<div class="window-buttons">'
                '<span class="btn red"></span>'
                '<span class="btn yellow"></span>'
                '<span class="btn green"></span>'
                '</div>'
            )

        footer_html = ""
        if config["show_footer"]:
            footer_html = (
                '<div class="footer">'
                '<span>{}</span><span>{}</span>'
                '</div>'.format(
                    html.escape(config["footer_text"]),
                    html.escape(datetime.now().strftime("%d %b %Y, %I:%M %p"))
                )
            )

        return """<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>{title}</title>
<style>
* {{ box-sizing: border-box; }}
html, body {{ margin: 0; padding: 0; background: transparent; }}
body {{
    margin: 0;
    padding: {page_padding}px;
    background: {page_bg};
    font-family: Arial, sans-serif;
    display: flex;
    align-items: center;
    justify-content: center;
    min-height: 100vh;
}}
.snapshot-wrapper {{
    display: inline-block;
    width: fit-content;
    min-width: 760px;
    max-width: {card_max_width}px;
    border-radius: {border_radius}px;
    overflow: hidden;
    border: 1px solid {border};
    background: {card_bg};
    box-shadow: 0 {shadow_spread}px {shadow_blur}px rgba(0, 0, 0, {shadow_alpha});
}}
.top-bar {{
    height: 52px;
    padding: 0 18px;
    display: flex;
    align-items: center;
    position: relative;
    background: {top_bar_bg};
    border-bottom: 1px solid {border};
}}
.window-buttons {{
    display: flex;
    gap: 8px;
    position: absolute;
    left: 18px;
}}
.btn {{ width: 12px; height: 12px; border-radius: 50%; display: inline-block; }}
.red {{ background: #ff5f57; }}
.yellow {{ background: #ffbd2e; }}
.green {{ background: #28c840; }}
.title {{
    width: 100%;
    text-align: center;
    color: {title_color};
    font-size: 13px;
    font-weight: 600;
    letter-spacing: 0.2px;
}}
.code-area {{
    background: {code_bg};
    padding: {padding}px;
    overflow: visible;
}}
table {{ border-collapse: collapse; width: auto; }}
td {{ vertical-align: top; }}
.line-number {{
    user-select: none;
    text-align: right;
    min-width: 42px;
    padding-right: 20px;
    color: {line_number};
    opacity: 0.72;
    font-family: {font_family};
    font-size: {font_size}px;
    line-height: 1.7;
    white-space: pre;
}}
.line-code {{
    color: {text};
    font-family: {font_family};
    font-size: {font_size}px;
    line-height: 1.7;
    white-space: {code_white_space};
    overflow-wrap: anywhere;
    word-break: break-word;
}}
.footer {{
    display: flex;
    justify-content: space-between;
    gap: 24px;
    padding: 10px 18px;
    background: {footer_bg};
    color: {footer_text};
    font-size: 11px;
    border-top: 1px solid {border};
}}
.tok-comment {{ color: {comment}; }}
.tok-tag {{ color: {tag}; }}
.tok-attr {{ color: {attr}; }}
.tok-value {{ color: {value}; }}
.tok-keyword {{ color: {keyword}; }}
.tok-string {{ color: {string}; }}
.tok-number {{ color: {number}; }}
.tok-selector {{ color: {selector}; }}
.tok-property {{ color: {property}; }}
.tok-punct {{ color: {punct}; }}
.tok-boolean {{ color: {boolean}; }}
.tok-type {{ color: {type_color}; }}
.tok-func {{ color: {func}; }}
</style>
</head>
<body>
<div class="snapshot-wrapper">
    <div class="top-bar">{buttons_html}<div class="title">{title}</div></div>
    <div class="code-area">{code_html}</div>
    {footer_html}
</div>
</body>
</html>
""".format(
            title=html.escape(header_title),
            page_padding=config["page_padding"],
            page_bg=config["page_background"],
            card_max_width=config["card_max_width"],
            border_radius=config["border_radius"],
            border=theme["border"],
            card_bg=theme["card_bg"],
            shadow_spread=config["shadow_spread"],
            shadow_blur=config["shadow_blur"],
            shadow_alpha=config["shadow_alpha"],
            top_bar_bg=theme["top_bar_bg"],
            title_color=theme["title_color"],
            code_bg=theme["code_bg"],
            padding=config["padding"],
            line_number=theme["line_number"],
            font_family=config["font_family"],
            font_size=config["font_size"],
            text=theme["text"],
            footer_bg=theme["footer_bg"],
            footer_text=theme["footer_text"],
            comment=theme["comment"],
            tag=theme["tag"],
            attr=theme["attr"],
            value=theme["value"],
            keyword=theme["keyword"],
            string=theme["string"],
            number=theme["number"],
            selector=theme["selector"],
            property=theme["property"],
            punct=theme["punct"],
            boolean=theme["boolean"],
            type_color=theme["type"],
            func=theme["func"],
            code_white_space=("pre-wrap" if config.get("wrap_long_lines", True) else "pre"),
            buttons_html=buttons_html,
            code_html=code_html,
            footer_html=footer_html
        )

    def render_code(self, code, language, show_line_numbers):
        rows = []

        for index, line in enumerate(code.split("\n"), start=1):
            highlighted = self.highlight_line(line, language)
            if highlighted == "":
                highlighted = "&nbsp;"

            if show_line_numbers:
                rows.append(
                    '<tr><td class="line-number">{}</td><td class="line-code">{}</td></tr>'.format(index, highlighted)
                )
            else:
                rows.append(
                    '<tr><td class="line-code">{}</td></tr>'.format(highlighted)
                )

        return "<table>{}</table>".format("".join(rows))

    def highlight_line(self, line, language):
        if language == "html":
            return self.highlight_html_line(line)
        if language == "css":
            return self.highlight_css_line(line)
        if language in ["javascript", "php", "java", "cpp", "csharp", "vb"]:
            return self.highlight_code_like(language, line)
        if language == "python":
            return self.highlight_python_line(line)
        if language == "sql":
            return self.highlight_sql_line(line)
        if language == "json":
            return self.highlight_json_line(line)
        if language == "bash":
            return self.highlight_bash_line(line)

        return html.escape(line)

    def highlight_code_like(self, language, line):
        keyword_map = {
            "javascript": r"\b(?:const|let|var|function|return|if|else|for|while|switch|case|break|continue|new|class|extends|import|from|export|default|async|await|try|catch|finally|throw|typeof|instanceof|this|null|undefined)\b",
            "php": r"\b(?:function|return|if|else|elseif|for|foreach|while|switch|case|break|continue|new|class|extends|public|private|protected|try|catch|finally|throw|null)\b",
            "java": r"\b(?:public|private|protected|class|interface|enum|static|void|int|double|float|boolean|char|new|return|if|else|for|while|switch|case|break|continue|try|catch|finally|throw|this|null|package|import)\b",
            "cpp": r"\b(?:int|float|double|char|bool|void|class|struct|return|if|else|for|while|switch|case|break|continue|namespace|using|new|delete|public|private|protected|nullptr|include)\b",
            "csharp": r"\b(?:using|namespace|class|public|private|protected|internal|static|void|int|string|bool|var|new|return|if|else|for|foreach|while|switch|case|break|continue|try|catch|finally|async|await|this|null)\b",
            "vb": r"\b(?:Dim|As|Sub|Function|Return|If|Then|Else|ElseIf|For|Each|While|Next|End|Class|Module|Public|Private|Protected|New|Try|Catch|Finally|Nothing)\b"
        }

        comment_map = {
            "javascript": [r"//.*$"],
            "php": [r"//.*$", r"#.*$"],
            "java": [r"//.*$"],
            "cpp": [r"//.*$"],
            "csharp": [r"//.*$"],
            "vb": [r"'.*$"]
        }

        return self.highlight_generic_line(
            line,
            comment_map.get(language, []),
            [r'"(?:\\.|[^"\\])*"', r"'(?:\\.|[^'\\])*'", r"`(?:\\.|[^`\\])*`"],
            r"\b\d+(?:\.\d+)?\b",
            keyword_map.get(language, ""),
            r"\b(?:true|false|True|False)\b",
            r"\b(?:string|int|bool|float|double|decimal|List|Dictionary|Task|Promise|Array|Object|DateTime|Integer|Boolean|Long|Short|Byte|Char)\b",
            r"\b([A-Za-z_][A-Za-z0-9_]*)\s*(?=\()"
        )

    def highlight_python_line(self, line):
        return self.highlight_generic_line(
            line,
            [r"#.*$"],
            [r'"(?:\\.|[^"\\])*"', r"'(?:\\.|[^'\\])*'"],
            r"\b\d+(?:\.\d+)?\b",
            r"\b(?:def|class|return|if|elif|else|for|while|break|continue|import|from|as|try|except|finally|raise|with|lambda|pass|yield|in|is|not|and|or|None)\b",
            r"\b(?:True|False)\b",
            r"\b(?:str|int|bool|float|list|dict|tuple|set)\b",
            r"\b([A-Za-z_][A-Za-z0-9_]*)\s*(?=\()"
        )

    def highlight_sql_line(self, line):
        return self.highlight_generic_line(
            line,
            [r"--.*$"],
            [r"'(?:''|[^'])*'"],
            r"\b\d+(?:\.\d+)?\b",
            r"\b(?:SELECT|FROM|WHERE|AND|OR|JOIN|LEFT|RIGHT|INNER|OUTER|ON|GROUP|BY|ORDER|INSERT|INTO|VALUES|UPDATE|SET|DELETE|CREATE|ALTER|DROP|TABLE|VIEW|AS|DISTINCT|TOP|NULL|IS|NOT|IN|LIKE|BETWEEN)\b",
            "",
            "",
            r"\b([A-Za-z_][A-Za-z0-9_]*)\s*(?=\()"
        )

    def highlight_bash_line(self, line):
        return self.highlight_generic_line(
            line,
            [r"#.*$"],
            [r'"(?:\\.|[^"\\])*"', r"'(?:\\.|[^'\\])*'"],
            r"\b\d+(?:\.\d+)?\b",
            r"\b(?:if|then|else|elif|fi|for|in|do|done|case|esac|function|return|while|export|local|echo|exit)\b",
            "",
            "",
            r"\b([A-Za-z_][A-Za-z0-9_]*)\s*(?=\()"
        )

    def highlight_json_line(self, line):
        text = html.escape(line)
        text = re.sub(r'(&quot;.*?&quot;)(\s*:)', r'<span class="tok-attr">\1</span><span class="tok-punct">\2</span>', text)
        text = re.sub(r':\s*(&quot;.*?&quot;)', r': <span class="tok-string">\1</span>', text)
        text = re.sub(r'\b(-?\d+(?:\.\d+)?)\b', r'<span class="tok-number">\1</span>', text)
        text = re.sub(r'\b(true|false)\b', r'<span class="tok-boolean">\1</span>', text)
        text = re.sub(r'\b(null)\b', r'<span class="tok-keyword">\1</span>', text)
        return text

    def highlight_generic_line(self, line, comment_patterns, string_patterns, number_pattern, keyword_pattern, type_pattern, type_names_pattern, function_pattern):
        placeholders = []
        raw = line

        def store_token(token_html):
            key = "@@TOKEN{}@@".format(len(placeholders))
            placeholders.append((key, token_html))
            return key

        for pattern in comment_patterns:
            def comment_repl(match):
                return store_token('<span class="tok-comment">{}</span>'.format(html.escape(match.group(0))))
            raw = re.sub(pattern, comment_repl, raw)

        for pattern in string_patterns:
            def string_repl(match):
                return store_token('<span class="tok-string">{}</span>'.format(html.escape(match.group(0))))
            raw = re.sub(pattern, string_repl, raw)

        text = html.escape(raw)

        if keyword_pattern:
            text = re.sub(keyword_pattern, r'<span class="tok-keyword">\g<0></span>', text)
        if type_pattern:
            text = re.sub(type_pattern, r'<span class="tok-boolean">\g<0></span>', text)
        if type_names_pattern:
            text = re.sub(type_names_pattern, r'<span class="tok-type">\g<0></span>', text)
        if number_pattern:
            text = re.sub(number_pattern, r'<span class="tok-number">\g<0></span>', text)
        if function_pattern:
            text = re.sub(function_pattern, r'<span class="tok-func">\1</span>', text)

        for key, value in placeholders:
            text = text.replace(html.escape(key), value)

        return text

    def highlight_css_line(self, line):
        stripped = line.strip()
        if stripped.startswith("/*") or stripped.startswith("*") or stripped.endswith("*/"):
            return '<span class="tok-comment">{}</span>'.format(html.escape(line))

        text = html.escape(line)
        text = re.sub(r'(@[a-zA-Z\-]+)', r'<span class="tok-keyword">\1</span>', text)
        text = re.sub(r'([.#]?[a-zA-Z_][\w\-\s>:+\[\]=&quot;\']*)(\s*\{)', r'<span class="tok-selector">\1</span><span class="tok-punct">\2</span>', text)
        text = re.sub(r'([a-zA-Z\-]+)(\s*:)', r'<span class="tok-property">\1</span><span class="tok-punct">\2</span>', text)
        text = re.sub(r'(#[0-9a-fA-F]{3,8})', r'<span class="tok-number">\1</span>', text)
        text = re.sub(r'\b(\d+(?:\.\d+)?(?:px|em|rem|%|vh|vw|s|ms)?)\b', r'<span class="tok-number">\1</span>', text)
        text = re.sub(r'(&quot;.*?&quot;)', r'<span class="tok-string">\1</span>', text)
        return text

    def highlight_html_line(self, line):
        result = []
        pos = 0
        token_re = re.compile(r'<!--.*?-->|</?[A-Za-z][^<>]*?>')

        for match in token_re.finditer(line):
            if match.start() > pos:
                result.append(html.escape(line[pos:match.start()]))

            token = match.group(0)
            if token.startswith("<!--"):
                result.append('<span class="tok-comment">{}</span>'.format(html.escape(token)))
            else:
                result.append(self.format_html_tag(token))

            pos = match.end()

        if pos < len(line):
            result.append(html.escape(line[pos:]))

        return "".join(result)

    def format_html_tag(self, tag_text):
        m = re.match(r'(<\/?)([A-Za-z][\w:\-]*)(.*?)(\/?>)$', tag_text)
        if not m:
            return html.escape(tag_text)

        open_part, tag_name, attrs_text, close_part = m.groups()

        return "".join([
            '<span class="tok-punct">{}</span>'.format(html.escape(open_part)),
            '<span class="tok-tag">{}</span>'.format(html.escape(tag_name)),
            self.format_html_attrs(attrs_text),
            '<span class="tok-punct">{}</span>'.format(html.escape(close_part))
        ])

    def format_html_attrs(self, attrs_text):
        result = []
        pos = 0
        attr_re = re.compile(r'(\s+)([A-Za-z_:][\w:.\-]*)(\s*=\s*)(".*?"|\'.*?\'|[^\s"\'=<>`]+)?')

        for match in attr_re.finditer(attrs_text):
            if match.start() > pos:
                result.append(html.escape(attrs_text[pos:match.start()]))

            spaces, name, eq, value = match.groups()
            result.append(html.escape(spaces))
            result.append('<span class="tok-attr">{}</span>'.format(html.escape(name)))

            if eq:
                result.append('<span class="tok-punct">{}</span>'.format(html.escape(eq)))

            if value is not None:
                result.append('<span class="tok-value">{}</span>'.format(html.escape(value)))

            pos = match.end()

        if pos < len(attrs_text):
            result.append(html.escape(attrs_text[pos:]))

        return "".join(result)

    def get_theme(self, name):
        themes = {
            "vscode-dark": {
                "page_bg": "linear-gradient(135deg, #162032, #0f172a)",
                "card_bg": "#1e1e1e",
                "top_bar_bg": "#2a2d2e",
                "code_bg": "#1e1e1e",
                "footer_bg": "#252526",
                "border": "rgba(255,255,255,0.08)",
                "title_color": "#ffffff",
                "text": "#d4d4d4",
                "line_number": "#858585",
                "footer_text": "#a1a1aa",
                "comment": "#6A9955",
                "tag": "#569CD6",
                "attr": "#9CDCFE",
                "value": "#CE9178",
                "keyword": "#C586C0",
                "string": "#CE9178",
                "number": "#B5CEA8",
                "selector": "#D7BA7D",
                "property": "#9CDCFE",
                "punct": "#d4d4d4",
                "boolean": "#569CD6",
                "type": "#4EC9B0",
                "func": "#DCDCAA"
            },
            "dracula": {
                "page_bg": "linear-gradient(135deg, #20152f, #0f1021)",
                "card_bg": "#282a36",
                "top_bar_bg": "#343746",
                "code_bg": "#282a36",
                "footer_bg": "#343746",
                "border": "rgba(255,255,255,0.08)",
                "title_color": "#f8f8f2",
                "text": "#f8f8f2",
                "line_number": "#6272a4",
                "footer_text": "#bd93f9",
                "comment": "#6272a4",
                "tag": "#8be9fd",
                "attr": "#50fa7b",
                "value": "#f1fa8c",
                "keyword": "#ff79c6",
                "string": "#f1fa8c",
                "number": "#bd93f9",
                "selector": "#ffb86c",
                "property": "#50fa7b",
                "punct": "#f8f8f2",
                "boolean": "#bd93f9",
                "type": "#8be9fd",
                "func": "#50fa7b"
            },
            "github-light": {
                "page_bg": "linear-gradient(135deg, #eef4ff, #d9e6f7)",
                "card_bg": "#ffffff",
                "top_bar_bg": "#f6f8fa",
                "code_bg": "#ffffff",
                "footer_bg": "#f6f8fa",
                "border": "rgba(31,35,40,0.10)",
                "title_color": "#24292f",
                "text": "#24292f",
                "line_number": "#8c959f",
                "footer_text": "#57606a",
                "comment": "#6e7781",
                "tag": "#0550ae",
                "attr": "#116329",
                "value": "#0a3069",
                "keyword": "#cf222e",
                "string": "#0a3069",
                "number": "#0550ae",
                "selector": "#953800",
                "property": "#8250df",
                "punct": "#24292f",
                "boolean": "#0550ae",
                "type": "#8250df",
                "func": "#8250df"
            },
            "midnight": {
                "page_bg": "linear-gradient(135deg, #020617, #111827)",
                "card_bg": "#020617",
                "top_bar_bg": "#030712",
                "code_bg": "#020617",
                "footer_bg": "#030712",
                "border": "rgba(255,255,255,0.08)",
                "title_color": "#f8fafc",
                "text": "#e5e7eb",
                "line_number": "#6b7280",
                "footer_text": "#94a3b8",
                "comment": "#64748b",
                "tag": "#60a5fa",
                "attr": "#22d3ee",
                "value": "#fca5a5",
                "keyword": "#c084fc",
                "string": "#fdba74",
                "number": "#bef264",
                "selector": "#fde68a",
                "property": "#67e8f9",
                "punct": "#e5e7eb",
                "boolean": "#93c5fd",
                "type": "#5eead4",
                "func": "#fcd34d"
            }
        }

        return themes.get(name, themes[DEFAULT_THEME])

    def write_temp_file(self, filename, content):
        path = os.path.join(tempfile.gettempdir(), filename)

        with open(path, "w", encoding="utf-8") as file:
            file.write(content)

        return path

    def get_output_png_path(self, save_to_desktop):
        filename = "codeshot-v54-{}.png".format(int(time.time()))

        if save_to_desktop:
            desktop = os.path.join(os.path.expanduser("~"), "Desktop")
            if os.path.isdir(desktop):
                return os.path.join(desktop, filename)

        return os.path.join(tempfile.gettempdir(), filename)

    def find_browser(self, configured_path):
        if configured_path and os.path.exists(configured_path):
            return configured_path

        candidates = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
        ]

        for path in candidates:
            if os.path.exists(path):
                return path

        for exe in ["chrome.exe", "msedge.exe"]:
            found = shutil.which(exe)
            if found:
                return found

        return None

    def render_png(self, browser_path, html_path, png_path, width, height):
        file_url = "file:///" + html_path.replace("\\", "/")

        command = [
            browser_path,
            "--headless=new",
            "--disable-gpu",
            "--hide-scrollbars",
            "--force-device-scale-factor=2",
            "--window-size={},{}".format(width, height),
            "--virtual-time-budget=1500",
            "--screenshot={}".format(png_path),
            file_url
        ]

        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                startupinfo=hidden_startupinfo()
            )

            try:
                stdout, stderr = process.communicate(timeout=30)
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate()
                return False, "Browser screenshot process timed out."

            if process.returncode != 0:
                try:
                    return False, stderr.decode("utf-8", errors="ignore")
                except Exception:
                    return False, str(stderr)

            if not os.path.exists(png_path):
                return False, "Browser finished but PNG file was not created."

            return True, "OK"

        except Exception as ex:
            return False, str(ex)

    def copy_png_to_clipboard(self, png_path):
        safe_path = png_path.replace("\\", "\\\\")
        script = """
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$path = "{path}"
if (!(Test-Path $path)) {{ throw "PNG not found: $path" }}
$fs = [System.IO.File]::Open($path, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read)
try {{
    $img = [System.Drawing.Image]::FromStream($fs)
    $bmp = New-Object System.Drawing.Bitmap $img
    [System.Windows.Forms.Clipboard]::SetImage($bmp)
    Start-Sleep -Milliseconds 300
}}
finally {{
    if ($img) {{ $img.Dispose() }}
    $fs.Dispose()
}}
""".format(path=safe_path)

        command = [
            "powershell",
            "-NoProfile",
            "-STA",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            script
        ]

        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                startupinfo=hidden_startupinfo()
            )

            try:
                stdout, stderr = process.communicate(timeout=20)
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate()
                return False, "PowerShell clipboard process timed out."

            if process.returncode != 0:
                try:
                    err = stderr.decode("utf-8", errors="ignore").strip()
                    if not err:
                        err = stdout.decode("utf-8", errors="ignore").strip()
                except Exception:
                    err = str(stderr)

                return False, err or "Unknown PowerShell clipboard error."

            return True, "OK"

        except Exception as ex:
            return False, str(ex)
