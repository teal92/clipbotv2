from pydantic import BaseModel,ConfigDict,Field
class LocalClipEdit(BaseModel):
 model_config=ConfigDict(extra='forbid')
 userId:str=Field(pattern=r'^[a-f0-9]{32}$')
 title:str=Field(min_length=1,max_length=100)
 description:str=Field(min_length=1,max_length=1000)
 start:float=Field(strict=True,allow_inf_nan=False,ge=0,le=305)
 end:float=Field(strict=True,allow_inf_nan=False,ge=0,le=305)
