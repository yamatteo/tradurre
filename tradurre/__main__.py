import uvicorn

from tradurre.config import HOST, PORT


def main():
    uvicorn.run("tradurre.app:app", host=HOST, port=PORT, reload=True)


if __name__ == "__main__":
    main()
