from pathlib import Path

from app.reference_data import load_reference_summary


def test_load_reference_summary_includes_excel_datasets():
    project_root = Path(__file__).resolve().parents[2]

    summary = load_reference_summary(project_root)

    assert "files" in summary
    assert "datasets" in summary
    assert "tooling_matrix" in summary

    datasets = summary["datasets"]
    dataset_names = {dataset["name"] for dataset in datasets}

    assert "Industrialisation_Process_Tooling_Matrix_EN.xlsx" in dataset_names
    assert "Quarterly_Global_Energy_Cost_Database_EN.xlsx" in dataset_names
    assert "Quarterly_Global_Labour_Cost_Database_EN.xlsx" in dataset_names


def test_load_reference_summary_reports_sheet_metadata():
    project_root = Path(__file__).resolve().parents[2]

    summary = load_reference_summary(project_root)
    tooling_matrix = summary["tooling_matrix"]

    assert tooling_matrix["sheet_name"] == "Process & Tool Matrix"
    assert tooling_matrix["row_count"] >= 20
    assert len(tooling_matrix["columns"]) >= 8
