"""ツアー"""
from __future__ import annotations




class TourMixin:
    """ツアー（Window が継承する）"""

    def tour_steps(self):
        from atelier.ui.tour import Step
        p = self.panels

        def show(key):
            return lambda: (p[key][0].show(), p[key][0].raise_())
        # はじめのツアーは 5 枚まで。前は 15 枚が続き、閉じたあとに機能ごとの案内が続けて出て長かった。
        # 欄と帯の案内は「ヘルプ」の「機能ごとの案内」（atelier/ui/tours.py の tour_panels・tour_bars）に分けた
        return [
            Step(lambda: None, "AtelIer へようこそ", "AI に頼んで描かせ、自分でも描き足せます。主な所を 5 枚で案内します。"),
            Step(lambda: p["chat"][0], "AI の欄", "「描く内容」に描きたい絵を、「禁止ワード」に描かない物を書いて「描く」を押します。\n"
                 "作風・模型・詳しい設定は見出しを押すと開きます。", show("chat")),
            Step(lambda: self.canvas, "キャンバス", "描いている途中の絵がここに出ます。\nホイールで拡大、Space を押しながらドラッグで動かせます。"),
            Step(lambda: self.tools, "道具", "ペン・消しゴム・塗りつぶしなどを選びます。\nアイコンにカーソルを重ねると、名前とキーが出ます。"),
            Step(lambda: self.menuBar(), "ほかの案内", "欄・帯・配置の案内は「ヘルプ」の「機能ごとの案内」にあります。\n"
                 "新しい案内が増えると、「ヘルプ」に印が付きます。"),
        ]

    def feature_tour(self, key: str, then=None) -> bool:
        """機能を初めて使うときの案内（atelier/ui/tours.py）。出したら閉じたあとに then を呼ぶ"""
        from atelier.ui import tours
        return tours.show(self, key, then)

    def tour_first(self, key: str, then) -> bool:
        """初めてなら案内を出して True（閉じたあとに then）。出さなければ then を呼ばずに False"""
        from atelier.ui import tours
        return tours.first(self, key, then)

    def start_tour(self):
        from atelier.ui.tour import Tour
        def closed():
            from atelier.ui import tours
            tours.hold(self)   # 閉じた直後に機能ごとの案内を続けて出さない（連鎖して長くなった）
            self.layout_store.setValue("tour_done", 1)
            self.hide_progress_if_idle(0)   # ツアーで見せた進みの欄を、描いていなければ戻す
        self.tour = Tour(self, self.tour_steps(), on_close=closed)
        self.tour.start()

    def maybe_tour(self):
        """初めて起動したときだけ、ツアーを出す。2 回目からは、まだ見ていない新しいツアーを 1 回だけ控えめに知らせる"""
        if not int(self.layout_store.value("tour_done", 0)):
            from atelier.ui import tours
            tours.mark_noticed(self)   # 初めての人には、はじめのツアーの終わりで「ヘルプ」に案内がある
            self.start_tour()
            return
        self.notice_new_tours()

    def notice_new_tours(self):
        from atelier.ui import tours
        fresh = tours.unnoticed(self)
        if fresh:
            tours.mark_noticed(self)
            self.notify(f"新しいツアーが {len(fresh)} つあります", "info", "「ヘルプ」の「新しいツアー」から見られます",
                        on_click=lambda: self.new_tours_menu.popup(self.mapToGlobal(self.rect().center())))

    def _fill_new_tours(self):
        """「ヘルプ」の「新しいツアー（n）」を、まだ見ていない新しい案内で作り直す"""
        from atelier.ui import tours
        m = self.new_tours_menu
        m.clear()
        cat = tours.catalog(self)
        fresh = tours.unseen_new(self)
        m.setTitle(f"新しいツアー（{len(fresh)}）" if fresh else "新しいツアー")
        for key in tours.NEW:
            a = m.addAction(("● " if key in fresh else "") + cat[key][0])
            a.setToolTip("まだ見ていない案内" if key in fresh else "見た案内（もう一度見られます）")
            a.triggered.connect(lambda _=False, k=key: (tours.show(self, k, force=True), self._fill_new_tours()))
