from rescue_crew import main


def test_main_runs(capsys):
    main()
    assert capsys.readouterr().out.strip() != ""
