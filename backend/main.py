import uvicorn

from api.server import app


def main():
    uvicorn.run(app, host="127.0.0.1", port=8731, log_level="info")


if __name__ == "__main__":
    main()
