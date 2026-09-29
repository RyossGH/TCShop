"""Tableau de bord : indicateurs, graphiques, alertes."""
from __future__ import annotations

from datetime import date, timedelta

from PySide6.QtCharts import (
    QBarCategoryAxis, QBarSet, QChart, QChartView, QPieSeries, QStackedBarSeries, QValueAxis,
)
from PySide6.QtCore import QMargins, Qt
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import QComboBox, QGridLayout, QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget

from ..constants import family_of

from .. import theme
from ..widgets import Card, DataTable, KpiCard, PageHeader, button, label, money, page_layout

REVENUE_SQL = """
SELECT date, total, cost_total, 'Boutique' AS channel FROM sales WHERE status = 'Validée'
UNION ALL
SELECT date, total, cost_total, 'En ligne' AS channel FROM orders WHERE status != 'Annulée'
"""

PIE_COLORS = ["#7c5cff", "#22c55e", "#f59e0b", "#38bdf8", "#ef4444", "#ec4899", "#14b8a6", "#a3a3a3"]


class DashboardPage(QWidget):
    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        inner = QWidget()
        scroll.setWidget(inner)
        outer.addWidget(scroll)
        lay = page_layout(inner)

        self.header = PageHeader("Tableau de bord", " ")
        self.header.add(button("Actualiser", self.refresh))
        self.header.add(button("+ Nouvelle vente", lambda: ctx.window.goto("pos"), "primary"))
        lay.addWidget(self.header)

        grid = QGridLayout()
        grid.setSpacing(12)
        self.k_today = KpiCard("CA aujourd'hui", "💶")
        self.k_month = KpiCard("CA 30 jours", "📈")
        self.k_margin = KpiCard("Marge brute 30 j", "💹")
        self.k_buys = KpiCard("Rachats 30 j", "🤝")
        self.k_stock = KpiCard("Valeur du stock", "🗃️")
        self.k_refs = KpiCard("Articles en stock", "🃏")
        self.k_orders = KpiCard("Commandes à traiter", "📦")
        self.k_credit = KpiCard("Crédit clients", "🎟️")
        for i, k in enumerate([self.k_today, self.k_month, self.k_margin, self.k_buys,
                               self.k_stock, self.k_refs, self.k_orders, self.k_credit]):
            grid.addWidget(k, i // 4, i % 4)
        lay.addLayout(grid)

        charts = QHBoxLayout()
        charts.setSpacing(12)
        c1 = Card()
        c1.lay.addWidget(label("Chiffre d'affaires — 30 derniers jours", "H2"))
        self.bar_view = QChartView()
        self.bar_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.bar_view.setStyleSheet("background: transparent; border: none;")
        self.bar_view.setMinimumHeight(290)
        c1.lay.addWidget(self.bar_view)
        charts.addWidget(c1, 3)
        c2 = Card()
        pie_head = QHBoxLayout()
        pie_head.addWidget(label("Répartition des ventes — 30 jours", "H2"), 1)
        self.pie_mode = QComboBox()
        self.pie_mode.addItems(["Par famille", "Par catégorie", "Par jeu"])
        self.pie_mode.currentIndexChanged.connect(lambda _i: self._pie_chart(self._d30))
        pie_head.addWidget(self.pie_mode)
        c2.lay.addLayout(pie_head)
        self.pie_view = QChartView()
        self.pie_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.pie_view.setStyleSheet("background: transparent; border: none;")
        self.pie_view.setMinimumHeight(290)
        c2.lay.addWidget(self.pie_view)
        charts.addWidget(c2, 2)
        lay.addLayout(charts)

        tables = QHBoxLayout()
        tables.setSpacing(12)
        t1 = Card()
        t1.lay.addWidget(label("🏆 Meilleures ventes (30 j)", "H2"))
        self.top = DataTable([("name", "Article", "text"), ("qty", "Qté", "int"), ("ca", "CA", "money")], stretch="name")
        self.top.setMinimumHeight(260)
        t1.lay.addWidget(self.top)
        tables.addWidget(t1)
        t2 = Card()
        t2.lay.addWidget(label("⚠️ Alertes de stock", "H2"))
        self.low = DataTable([("name", "Article", "text"), ("location", "Empl.", "text"),
                              ("quantity", "Stock", "qty"), ("min_stock", "Min.", "int")], stretch="name")
        self.low.setMinimumHeight(260)
        self.low.record_activated.connect(lambda r: ctx.window.goto("inventory", select_id=r["id"]))
        t2.lay.addWidget(self.low)
        tables.addWidget(t2)
        t3 = Card()
        t3.lay.addWidget(label("🕘 Dernières opérations", "H2"))
        self.recent = DataTable([("date", "Date", "date"),
                                 ("label", "Détail", "text"), ("total", "Montant", "money")], stretch="label")
        self.recent.setMinimumHeight(260)
        t3.lay.addWidget(self.recent)
        tables.addWidget(t3)
        lay.addLayout(tables)
        lay.addStretch(1)

    # ------------------------------------------------------------------
    def refresh(self):
        db = self.ctx.db
        today = date.today()
        d30 = (today - timedelta(days=29)).isoformat()
        shop = db.setting("shop_name")
        self._set_subtitle(f"{shop} · {today.strftime('%d/%m/%Y')}")

        t = db.one(f"SELECT COALESCE(SUM(total),0) s, COUNT(*) n FROM ({REVENUE_SQL}) WHERE date >= ?",
                   (today.isoformat(),))
        self.k_today.set(money(t["s"]), f"{t['n']} transaction(s)")
        m = db.one(f"SELECT COALESCE(SUM(total),0) s, COALESCE(SUM(cost_total),0) c, COUNT(*) n "
                   f"FROM ({REVENUE_SQL}) WHERE date >= ?", (d30,))
        basket = m["s"] / m["n"] if m["n"] else 0
        self.k_month.set(money(m["s"]), f"{m['n']} ventes · panier moyen {money(basket)}")
        margin = m["s"] - m["c"]
        self.k_margin.set(money(margin), f"{(margin / m['s'] * 100) if m['s'] else 0:.0f} % du CA",
                          "success" if margin >= 0 else "danger")
        b = db.one("SELECT COALESCE(SUM(total),0) s, COUNT(*) n FROM buys WHERE date >= ?", (d30,))
        self.k_buys.set(money(b["s"]), f"{b['n']} rachat(s)")
        st = db.one("SELECT COALESCE(SUM(quantity*price),0) v, COALESCE(SUM(quantity*cost),0) c, "
                    "COALESCE(SUM(quantity),0) q, COUNT(*) n FROM products WHERE quantity > 0 AND track_stock = 1")
        self.k_stock.set(money(st["v"]), f"coût d'achat {money(st['c'])}")
        self.k_refs.set(f"{int(st['q']):,}".replace(",", " "), f"{st['n']} références")
        o = db.val("SELECT COUNT(*) FROM orders WHERE status IN ('À préparer', 'Préparée')", default=0)
        self.k_orders.set(str(o), "à préparer / expédier", "warning" if o else None)
        cr = db.val("SELECT COALESCE(SUM(credit),0) FROM customers", default=0)
        self.k_credit.set(money(cr), "en circulation")

        self._bar_chart(d30, today)
        self._d30 = d30
        self._pie_chart(d30)

        self.top.set_rows(db.q("""
            SELECT name, SUM(qty) qty, SUM(qty*unit_price) ca FROM (
              SELECT si.name, si.qty, si.unit_price FROM sale_items si JOIN sales s ON s.id = si.sale_id
               WHERE s.status = 'Validée' AND s.date >= ?
              UNION ALL
              SELECT oi.name, oi.qty, oi.unit_price FROM order_items oi JOIN orders o ON o.id = oi.order_id
               WHERE o.status != 'Annulée' AND o.date >= ?)
            GROUP BY name ORDER BY ca DESC LIMIT 15""", (d30, d30)))
        self.low.set_rows(db.q("""SELECT id, name, location, quantity, min_stock FROM products
            WHERE track_stock = 1 AND ((min_stock > 0 AND quantity <= min_stock) OR quantity < 0)
            ORDER BY quantity LIMIT 100"""))
        self.recent.set_rows(db.q("""
            SELECT date, 'Vente ' || number || CASE WHEN status='Remboursée' THEN ' (remboursée)' ELSE '' END label, total FROM sales
            UNION ALL SELECT date, 'Rachat ' || number || ' · ' || COALESCE(customer_name,''), -total FROM buys
            UNION ALL SELECT date, 'Commande ' || number || ' · ' || channel || ' · ' || status, total FROM orders
            ORDER BY date DESC LIMIT 30"""))

    def _set_subtitle(self, text):
        labels = [l for l in self.header.findChildren(QLabel) if l.objectName() == "Muted"]
        if labels:
            labels[0].setText(text)

    def _style_chart(self, chart: QChart):
        chart.setBackgroundVisible(False)
        chart.setPlotAreaBackgroundVisible(False)
        chart.setMargins(QMargins(0, 0, 0, 0))
        chart.legend().setLabelColor(QColor(theme.c("text")))
        chart.setAnimationOptions(QChart.AnimationOption.SeriesAnimations)

    def _bar_chart(self, d30: str, today: date):
        rows = {r["d"]: r for r in self.ctx.db.q(
            f"SELECT substr(date,1,10) d, SUM(CASE WHEN channel='Boutique' THEN total ELSE 0 END) shop, "
            f"SUM(CASE WHEN channel='En ligne' THEN total ELSE 0 END) web FROM ({REVENUE_SQL}) "
            f"WHERE date >= ? GROUP BY d", (d30,))}
        shop, web = QBarSet("Boutique"), QBarSet("En ligne")
        shop.setColor(QColor(theme.c("accent")))
        web.setColor(QColor(theme.c("info")))
        shop.setBorderColor(QColor(0, 0, 0, 0))
        web.setBorderColor(QColor(0, 0, 0, 0))
        cats, top = [], 0.0
        for i in range(30):
            d = today - timedelta(days=29 - i)
            r = rows.get(d.isoformat())
            s, w = (r["shop"], r["web"]) if r else (0, 0)
            shop.append(s)
            web.append(w)
            top = max(top, s + w)
            cats.append(d.strftime("%d/%m"))
        series = QStackedBarSeries()
        series.append(shop)
        series.append(web)
        series.setBarWidth(0.8)
        chart = QChart()
        chart.addSeries(series)
        self._style_chart(chart)
        ax = QBarCategoryAxis()
        ax.append(cats)
        ax.setLabelsColor(QColor(theme.c("muted")))
        ax.setLabelsAngle(-90)
        f = QFont()
        f.setPointSizeF(7.5)
        ax.setLabelsFont(f)
        ax.setGridLineVisible(False)
        ay = QValueAxis()
        ay.setRange(0, max(10.0, top * 1.15))
        ay.setLabelFormat("%.0f")
        ay.setTitleText("€")
        ay.setTitleBrush(QColor(theme.c("muted")))
        ay.setLabelsColor(QColor(theme.c("muted")))
        ay.setGridLineColor(QColor(theme.c("border")))
        chart.addAxis(ax, Qt.AlignmentFlag.AlignBottom)
        chart.addAxis(ay, Qt.AlignmentFlag.AlignLeft)
        series.attachAxis(ax)
        series.attachAxis(ay)
        chart.legend().setAlignment(Qt.AlignmentFlag.AlignTop)
        old = self.bar_view.chart()
        self.bar_view.setChart(chart)
        if old is not None:
            old.deleteLater()

    def _pie_chart(self, d30: str):
        rows = self.ctx.db.q("""
            SELECT COALESCE(NULLIF(p.game,''), 'Divers') game, COALESCE(p.category, 'Divers') category,
                   SUM(x.qty*x.unit_price) ca FROM (
              SELECT si.product_id, si.qty, si.unit_price FROM sale_items si JOIN sales s ON s.id = si.sale_id
               WHERE s.status = 'Validée' AND s.date >= ?
              UNION ALL
              SELECT oi.product_id, oi.qty, oi.unit_price FROM order_items oi JOIN orders o ON o.id = oi.order_id
               WHERE o.status != 'Annulée' AND o.date >= ?) x
            LEFT JOIN products p ON p.id = x.product_id GROUP BY game, category""", (d30, d30))
        mode = self.pie_mode.currentIndex()
        agg: dict[str, float] = {}
        for r in rows:
            key = (family_of(r["category"]) if r["category"] != "Divers" else "Divers") if mode == 0 else \
                r["category"] if mode == 1 else (r["game"] if family_of(r["category"]) in ("Cartes à l'unité", "TCG scellé")
                                                 else "Hors TCG")
            agg[key] = agg.get(key, 0) + (r["ca"] or 0)
        rows = [dict(game=k, ca=v) for k, v in sorted(agg.items(), key=lambda kv: -kv[1])]
        series = QPieSeries()
        series.setHoleSize(0.55)
        total = sum(r["ca"] or 0 for r in rows) or 1
        for i, r in enumerate(rows[:7]):
            sl = series.append(f"{r['game']}  {r['ca'] / total * 100:.0f} %", r["ca"] or 0)
            sl.setColor(QColor(PIE_COLORS[i % len(PIE_COLORS)]))
            sl.setBorderColor(QColor(theme.c("panel")))
        if len(rows) > 7:
            rest = sum(r["ca"] or 0 for r in rows[7:])
            sl = series.append(f"Autres  {rest / total * 100:.0f} %", rest)
            sl.setColor(QColor(PIE_COLORS[-1]))
        chart = QChart()
        chart.addSeries(series)
        self._style_chart(chart)
        chart.legend().setAlignment(Qt.AlignmentFlag.AlignRight)
        if not rows:
            chart.setTitle("Aucune vente sur la période")
            chart.setTitleBrush(QColor(theme.c("muted")))
        old = self.pie_view.chart()
        self.pie_view.setChart(chart)
        if old is not None:
            old.deleteLater()
