"""Dark theme palette + QSS loader."""

PALETTE = {
    "dark": {
        "bg": "#0a0d10", "bg2": "#0f1317", "panel": "#12171c", "panel2": "#171d23",
        "panel3": "#1c232a", "line": "#242c34", "line2": "#2e3842",
        "text": "#d8e0e6", "textDim": "#8b96a1", "textMute": "#5c6771",
        "accent": "#d4a84b", "accent2": "#e5b85b",
        "ok": "#6fb56a", "warn": "#d4a84b", "alert": "#d86a5b",
        "info": "#5a9fb8", "alertSoft": "#3a1f1b",
    },
    "light": {
        "bg": "#ece8e0", "bg2": "#e2ddd2", "panel": "#f3efe7", "panel2": "#e8e2d5",
        "panel3": "#ddd6c6", "line": "#c9c2b2", "line2": "#b8b1a0",
        "text": "#1a1f24", "textDim": "#4a5058", "textMute": "#7a808a",
        "accent": "#8a6514", "accent2": "#7a580f",
        "ok": "#3d7a38", "warn": "#8a6514", "alert": "#a24234",
        "info": "#2a6a82", "alertSoft": "#e8d5cf",
    },
    "tactical": {
        "bg": "#0a0f0a", "bg2": "#0c140c", "panel": "#0e170e", "panel2": "#121d12",
        "panel3": "#162516", "line": "#1e2e1e", "line2": "#2a3d2a",
        "text": "#c8e0c4", "textDim": "#7ea17a", "textMute": "#4e6a4a",
        "accent": "#a8d96c", "accent2": "#bde08a",
        "ok": "#7bc04a", "warn": "#c9b948", "alert": "#d86a5b",
        "info": "#5fa8a0", "alertSoft": "#2a1a1a",
    },
}


def qss(theme_name: str) -> str:
    p = PALETTE[theme_name]
    return f"""
    QWidget {{
        background: {p['panel']};
        color: {p['text']};
        font-family: 'Inter', 'Segoe UI', 'Helvetica Neue', sans-serif;
        font-size: 13px;
    }}
    QMainWindow {{ background: {p['bg']}; }}
    QWidget#app {{ background: {p['bg']}; }}

    /* Mono helper */
    QLabel[role="mono"], QLabel[role="monoDim"], QLabel[role="monoMute"],
    QLabel[role="monoSmall"], QLabel[role="monoTiny"] {{
        font-family: 'JetBrains Mono', 'Menlo', 'Consolas', monospace;
    }}
    QLabel[role="monoDim"] {{ color: {p['textDim']}; }}
    QLabel[role="monoMute"] {{ color: {p['textMute']}; font-size: 10px; letter-spacing: 1px; }}
    QLabel[role="monoSmall"] {{ font-size: 10px; color: {p['textDim']}; }}
    QLabel[role="monoTiny"] {{ font-size: 9px; color: {p['textMute']}; letter-spacing: 1px; }}
    QLabel[role="panelTitle"] {{
        font-family: 'JetBrains Mono', monospace;
        font-size: 10px; color: {p['textDim']};
        letter-spacing: 2px; font-weight: 500;
    }}
    QLabel[role="brand"] {{
        font-family: 'JetBrains Mono', monospace;
        font-size: 12px; letter-spacing: 2px; color: {p['text']};
    }}
    QLabel[role="statLabel"] {{
        font-family: 'JetBrains Mono', monospace;
        font-size: 9px; color: {p['textMute']}; letter-spacing: 1.5px;
    }}
    QLabel[role="statValue"] {{
        font-family: 'JetBrains Mono', monospace;
        font-size: 13px; color: {p['text']};
    }}
    QLabel[role="cellLabel"] {{
        font-family: 'JetBrains Mono', monospace;
        font-size: 9px; color: {p['textMute']}; letter-spacing: 1.5px;
    }}
    QLabel[role="cellValue"] {{
        font-family: 'JetBrains Mono', monospace;
        font-size: 13px; color: {p['text']};
    }}

    /* Panels */
    QFrame#panel {{
        background: {p['panel']};
        border: 1px solid {p['line']};
    }}
    QFrame#panelHead {{
        background: {p['bg2']};
        border: none;
        border-bottom: 1px solid {p['line']};
        min-height: 32px; max-height: 32px;
    }}

    /* Titlebar */
    QFrame#titlebar {{
        background: {p['panel2']};
        border-bottom: 1px solid {p['line']};
        min-height: 36px; max-height: 36px;
    }}
    QLabel#statusPill {{
        font-family: 'JetBrains Mono', monospace;
        font-size: 10px; color: {p['textDim']};
        padding: 3px 8px;
        border: 1px solid {p['line2']};
        border-radius: 3px;
        background: {p['panel']};
    }}

    /* Tabs bar */
    QFrame#tabsbar {{
        background: {p['bg2']};
        border-bottom: 1px solid {p['line']};
        min-height: 36px; max-height: 36px;
    }}
    QPushButton[role="tab"] {{
        background: transparent;
        color: {p['textMute']};
        border: 1px solid transparent;
        border-bottom: none;
        padding: 8px 14px 7px;
        font-family: 'JetBrains Mono', monospace;
        font-size: 11px;
        letter-spacing: 1.4px;
    }}
    QPushButton[role="tab"]:hover {{ color: {p['textDim']}; }}
    QPushButton[role="tab"][active="true"] {{
        color: {p['text']};
        background: {p['panel']};
        border-color: {p['line']};
    }}

    /* Statusbar */
    QFrame#statusbar {{
        background: {p['bg2']};
        border-top: 1px solid {p['line']};
        min-height: 24px; max-height: 24px;
    }}
    QLabel[role="sbItem"] {{
        font-family: 'JetBrains Mono', monospace;
        font-size: 10px; color: {p['textMute']}; letter-spacing: 0.5px;
    }}

    /* Generic tool button (panel head actions, chips) */
    QPushButton[role="tool"] {{
        background: transparent;
        color: {p['textMute']};
        border: 1px solid {p['line2']};
        padding: 3px 8px; border-radius: 2px;
        font-family: 'JetBrains Mono', monospace;
        font-size: 10px; letter-spacing: 1px;
        min-height: 20px;
    }}
    QPushButton[role="tool"]:hover {{ color: {p['text']}; border-color: {p['textMute']}; }}
    QPushButton[role="tool"][active="true"] {{
        color: {p['accent']}; border-color: {p['accent']};
    }}

    QPushButton[role="chip"] {{
        background: {p['panel2']};
        color: {p['textDim']};
        border: 1px solid {p['line2']};
        padding: 5px 10px; border-radius: 2px;
        font-family: 'JetBrains Mono', monospace;
        font-size: 10px; letter-spacing: 1px;
    }}
    QPushButton[role="chip"]:hover {{ color: {p['text']}; }}
    QPushButton[role="chip"][active="true"] {{
        color: {p['accent']}; border-color: {p['accent']};
    }}

    QPushButton[role="btn"] {{
        background: {p['panel2']};
        color: {p['text']};
        border: 1px solid {p['line2']};
        padding: 9px 14px;
        border-radius: 2px;
        font-family: 'JetBrains Mono', monospace;
        font-size: 11px; letter-spacing: 1.4px;
    }}
    QPushButton[role="btn"]:hover {{ border-color: {p['textMute']}; }}
    QPushButton[role="btnPrimary"] {{
        background: {p['accent']};
        color: #1a1511;
        border: 1px solid {p['accent']};
        padding: 9px 14px;
        border-radius: 2px;
        font-family: 'JetBrains Mono', monospace;
        font-size: 11px; letter-spacing: 1.4px;
    }}
    QPushButton[role="btnPrimary"]:hover {{ background: {p['accent2']}; }}

    /* Node card */
    QFrame[role="nodeCard"] {{
        background: {p['panel2']};
        border: 1px solid {p['line']};
        border-radius: 3px;
    }}
    QFrame[role="nodeCard"]:hover {{ border: 1px solid {p['line2']}; }}
    QFrame[role="nodeCard"][selected="true"] {{
        background: {p['panel3']};
        border: 1px solid {p['accent']};
    }}
    QFrame[role="nodeCard"][triggered="true"] {{
        border: 1px solid {p['alert']};
    }}
    QLabel[role="nodeId"] {{
        font-family: 'JetBrains Mono', monospace;
        font-size: 11px; color: {p['text']}; letter-spacing: 0.5px;
    }}
    QLabel[role="nodeSub"] {{
        font-family: 'JetBrains Mono', monospace;
        font-size: 9px; color: {p['textMute']}; letter-spacing: 1px;
    }}
    QLabel[role="nodeStatus"] {{
        font-family: 'JetBrains Mono', monospace;
        font-size: 9px; letter-spacing: 1.5px;
    }}

    /* Ticker row */
    QFrame[role="tickerItem"] {{
        background: transparent;
        border-bottom: 1px solid {p['line']};
    }}
    QFrame[role="tickerItem"]:hover {{ background: {p['panel2']}; }}
    QLabel[role="tickerTitle"] {{
        font-family: 'JetBrains Mono', monospace;
        font-size: 11px; color: {p['text']};
    }}
    QLabel[role="tickerMeta"] {{
        font-family: 'JetBrains Mono', monospace;
        font-size: 10px; color: {p['textMute']};
    }}
    QLabel[role="tickerTime"] {{
        font-family: 'JetBrains Mono', monospace;
        font-size: 10px; color: {p['textMute']};
    }}

    /* Strip items */
    QFrame[role="stripItem"] {{
        background: {p['panel']};
        border-right: 1px solid {p['line']};
    }}
    QFrame[role="stripItem"]:hover {{ background: {p['panel2']}; }}

    /* Tables */
    QTableView, QHeaderView, QTableWidget {{
        background: {p['panel']};
        color: {p['text']};
        font-family: 'JetBrains Mono', monospace;
        font-size: 11px;
        border: none;
        gridline-color: {p['line']};
        selection-background-color: {p['panel3']};
        selection-color: {p['text']};
    }}
    QHeaderView::section {{
        background: {p['bg2']};
        color: {p['textMute']};
        border: none;
        border-bottom: 1px solid {p['line']};
        padding: 8px 12px;
        font-size: 10px;
        letter-spacing: 1.5px;
    }}
    QTableView::item {{ padding: 6px 10px; border-bottom: 1px solid {p['line']}; }}
    QTableView::item:hover {{ background: {p['panel2']}; }}

    /* Modal / dialog */
    QDialog#eventDialog {{ background: {p['panel']}; border: 1px solid {p['line2']}; }}
    QFrame#modalHead {{
        background: {p['bg2']};
        border-bottom: 1px solid {p['line']};
        min-height: 44px; max-height: 44px;
    }}
    QLabel#modalId {{
        font-family: 'JetBrains Mono', monospace;
        font-size: 12px; color: {p['text']}; letter-spacing: 1px;
    }}
    QLabel[role="sevPill"] {{
        font-family: 'JetBrains Mono', monospace;
        font-size: 10px; letter-spacing: 1.5px;
        padding: 3px 8px; border-radius: 2px;
        color: white; background: {p['alert']};
    }}
    QLabel[role="sevPill"][sev="med"] {{ background: {p['accent']}; color: #0a0f0a; }}
    QLabel[role="sevPill"][sev="info"] {{ background: {p['info']}; color: white; }}

    QFrame[role="metaCell"] {{
        background: {p['panel2']};
        border: none;
    }}

    /* Toolbar (inside tabs) */
    QFrame#eventsToolbar {{
        background: {p['bg2']};
        border-bottom: 1px solid {p['line']};
        min-height: 40px; max-height: 40px;
    }}

    /* Scroll areas (blend with panel) */
    QScrollArea, QScrollArea > QWidget > QWidget {{
        background: {p['panel']};
        border: none;
    }}
    QScrollBar:vertical {{
        background: {p['bg2']}; width: 10px; border: none;
    }}
    QScrollBar::handle:vertical {{
        background: {p['line2']}; border-radius: 3px; min-height: 30px;
    }}
    QScrollBar::handle:vertical:hover {{ background: {p['textMute']}; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QScrollBar:horizontal {{
        background: {p['bg2']}; height: 10px; border: none;
    }}
    QScrollBar::handle:horizontal {{
        background: {p['line2']}; border-radius: 3px; min-width: 30px;
    }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

    /* Toast */
    QFrame[role="toast"] {{
        background: {p['panel2']};
        border: 1px solid {p['alert']};
        border-left: 3px solid {p['alert']};
        border-radius: 2px;
    }}
    QFrame[role="toast"][kind="info"] {{
        border-color: {p['info']};
        border-left: 3px solid {p['info']};
    }}

    /* Gallery cards */
    QFrame[role="gCard"] {{
        background: {p['panel2']};
        border: 1px solid {p['line']};
        border-radius: 3px;
    }}
    QFrame[role="gCard"]:hover {{ border: 1px solid {p['line2']}; }}

    /* Signals row */
    QFrame[role="signalRow"] {{
        background: {p['panel']};
        border-bottom: 1px solid {p['line']};
    }}

    /* Ack tag */
    QLabel[role="ackTag"] {{
        font-family: 'JetBrains Mono', monospace;
        font-size: 9px; letter-spacing: 1.5px;
        padding: 2px 6px; border-radius: 2px;
        color: {p['textMute']};
        border: 1px solid {p['line2']};
    }}
    QLabel[role="ackTag"][ack="true"] {{
        color: {p['ok']}; border-color: {p['ok']};
    }}
    """
