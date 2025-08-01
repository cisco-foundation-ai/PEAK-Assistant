from utils import find_dotenv_file


def test_find_dotenv_file():
    """Test that find_dotenv_file correctly identifies the .env file"""
    # Assuming the test is run in a directory where a .env file exists
    env_file = find_dotenv_file()
    assert env_file is not None, "Expected to find a .env file"
    assert env_file.endswith(".env"), "Expected the found file to be a .env file"
