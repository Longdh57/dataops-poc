"""Phan logic cua Export Job — chay duoc ma khong can BigQuery.

Ba thu de sai nhat deu nam o day: ap override, tinh lai thi phan, va cat
sheet khi vuot gioi han cua Excel.
"""

from conftest import export_main

EXCEL_MAX_ROWS = export_main.EXCEL_MAX_ROWS
apply_group = export_main.apply_group
stream_groups = export_main.stream_groups
write_csv = export_main.write_csv


class Row:
    """Gia lap mot dong tra ve tu BigQuery."""

    def __init__(self, year, state, gender, name, number, market_share):
        self.year, self.state, self.gender = year, state, gender
        self.name, self.number, self.market_share = name, number, market_share


def nhom(*rows):
    return [{"year": r.year, "state": r.state, "gender": r.gender, "name": r.name,
             "number": r.number, "market_share": r.market_share, "da_sua": ""} for r in rows]


def test_khong_co_override_thi_giu_nguyen_so_cua_nguon():
    g = nhom(Row(2021, "CA", "F", "Emma", 60, 0.6),
             Row(2021, "CA", "F", "Olivia", 40, 0.4))
    out = apply_group(g, {})
    assert [r[4] for r in out] == [60, 40]
    assert [r[5] for r in out] == ["0.6000000000", "0.4000000000"]
    assert [r[6] for r in out] == ["", ""]


def test_co_override_thi_thi_phan_duoc_tinh_lai_cho_ca_nhom():
    """Day la cho de bo sot nhat: sua mot o thi thi phan cua CA NHOM doi.

    Neu chi thay so ma giu nguyen thi phan cu, khach cong lai se khong ra
    100% va se hoi tai sao.
    """
    g = nhom(Row(2021, "CA", "F", "Emma", 60, 0.6),
             Row(2021, "CA", "F", "Olivia", 40, 0.4))
    out = apply_group(g, {(2021, "CA", "F", "Emma"): 160})

    assert [r[4] for r in out] == [160, 40]
    assert [r[6] for r in out] == ["x", ""]
    tong = sum(float(r[5]) for r in out)
    assert abs(tong - 1.0) < 1e-9, "thi phan cong lai phai tron 100%"
    assert float(out[0][5]) == 0.8


def test_moi_nhom_duoc_tinh_rieng():
    rows = [Row(2021, "CA", "F", "Emma", 60, 0.6), Row(2021, "CA", "F", "Olivia", 40, 0.4),
            Row(2021, "TX", "M", "Liam", 50, 0.5), Row(2021, "TX", "M", "Noah", 50, 0.5)]
    out = list(stream_groups(rows, {(2021, "CA", "F", "Emma"): 160}))

    assert len(out) == 4
    # Nhom TX khong ai dong toi -> giu nguyen so cua nguon
    assert [r[5] for r in out[2:]] == ["0.5000000000", "0.5000000000"]


def test_ghi_csv_du_dong_va_du_tieu_de(tmp_path):
    rows = list(stream_groups([Row(2021, "CA", "F", "Emma", 60, 0.6)], {}))
    path = tmp_path / "x.csv"
    n, canh_bao = write_csv(str(path), rows)

    assert n == 1 and canh_bao is None
    dong = path.read_text().splitlines()
    assert dong[0].startswith("year,state,gender,name,number,market_share,da_sua")
    assert dong[1] == "2021,CA,F,Emma,60,0.6000000000,"


def test_xlsx_vuot_gioi_han_thi_tach_sheet_chu_khong_cat_bot(tmp_path, monkeypatch):
    """Gia gioi han xuong 5 dong de khoi phai sinh mot trieu dong that."""
    monkeypatch.setattr(export_main, "EXCEL_MAX_ROWS", 5)
    from openpyxl import load_workbook

    rows = [[2021, "CA", "F", f"Ten{i}", i, "0.1", ""] for i in range(12)]
    path = tmp_path / "x.xlsx"
    n, canh_bao = export_main.write_xlsx(str(path), rows)

    assert n == 12, "khong duoc cat bot dong nao"
    assert canh_bao and "tach thanh 3 sheet" in canh_bao

    wb = load_workbook(path)
    assert wb.sheetnames == ["Trang 1", "Trang 2", "Trang 3"]
    # Moi sheet co tieu de rieng, 4 dong du lieu, 4 dong, 4 dong
    assert [ws.max_row for ws in wb.worksheets] == [5, 5, 5]
    assert wb["Trang 2"].cell(row=1, column=1).value == "year"


def test_gioi_han_that_la_cua_excel():
    assert EXCEL_MAX_ROWS == 1_048_576
