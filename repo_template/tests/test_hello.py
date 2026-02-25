from repo_template.cli import main


def test_main() -> None:
    hello = main()
    assert hello.name == "Wei"
    assert hello.content == "Hello, World!"
