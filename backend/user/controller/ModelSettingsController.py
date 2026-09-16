from common.JWTDecode import get_current_user
from fastapi import APIRouter, Depends

from user.service.UserModelService import ModelSettingsRequest


class ModelSettingsController:
    def __init__(self, service):
        self.service = service
        self.router = APIRouter(tags=["account"])
        self.router.add_api_route("/model-settings", self.get, methods=["GET"])
        self.router.add_api_route("/model-settings", self.save, methods=["POST"])
        self.router.add_api_route("/model-settings", self.delete, methods=["DELETE"])

    def get(self, user=Depends(get_current_user)):
        return self.service.public(user["account_id"])

    def save(self, body: ModelSettingsRequest, user=Depends(get_current_user)):
        return self.service.save(user["account_id"], body)

    def delete(self, user=Depends(get_current_user)):
        return self.service.delete(user["account_id"])
