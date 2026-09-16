from Application import MedicalApplication
from common.Settings import Settings

app = MedicalApplication().create()

if __name__ == "__main__":
    import uvicorn

    config = Settings()
    uvicorn.run("main:app", host=config.host, port=config.port, access_log=False)
