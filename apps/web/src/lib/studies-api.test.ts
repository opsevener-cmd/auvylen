import {describe,expect,it} from "vitest";
import {allowedApiPath} from "./api-proxy-policy";
import {requestError} from "./account-api";
import {studyErrors,studyAssignmentSchema,studyStatusSchema} from "./studies-api";
import {translate} from "./i18n/catalog";
const id="12345678-1234-4234-9234-123456789abc";
describe("private study contracts and proxy boundary",()=>{
  it("allows only explicit workflow endpoints, including isolated native preview",()=>{
    for(const suffix of ["","/status","/join","/resolve-invite",`/${id}`,`/${id}/consent`,`/${id}/action`,`/${id}/withdraw`,`/${id}/receipts`,`/${id}/audit`,`/${id}/quality`,`/${id}/members/${id}/review`,`/${id}/photos`,`/${id}/photos/${id}/content`,`/${id}/photos/${id}/delete`,`/${id}/photos/${id}/review`,`/${id}/assignments`,`/${id}/assignments/${id}/content`,`/${id}/assignments/${id}/view`,`/${id}/assignments/${id}/rating`,`/${id}/exports`,`/${id}/exports/${id}`,`/${id}/exports/${id}/content`]) expect(allowedApiPath(`v1/research/studies${suffix}`),suffix).toBe(true);
    for(const suffix of ["/public","/../owner/users",`/${id}/holdout/export`,`/${id}/weights`,`/${id}/photos/${id}`,`/${id}/members/${id}/login`,`/${id}/exports/${id}/extra`]) expect(allowedApiPath(`v1/research/studies${suffix}`),suffix).toBe(false);
    for(const suffix of ["status","jobs",`jobs/${id}`,`jobs/${id}/delete`]) expect(allowedApiPath(`v1/research/native-preview/${suffix}`)).toBe(true);
    expect(allowedApiPath("v1/research/native-preview/weights")).toBe(false);
  });
  it("localizes safe failures without rendering arbitrary server text",()=>{
    for(const [code,message] of Object.entries(studyErrors)){
      expect(requestError("/research/studies",409,JSON.stringify({detail:code})).message).toBe(message);
      expect(translate("zh-CN",message)).not.toBe(message);
    }
    for(const detail of ["private@example.test","__proto__","constructor",{secret:"never render"}]) expect(requestError("/research/studies",503,JSON.stringify({detail})).message).toBe("Service temporarily unavailable.");
  });
  it("retains disabled consumer scoring and hides blind-repeat metadata",()=>{
    expect(studyStatusSchema.safeParse({enabled:true,real_collection_enabled:false,owner:false,consumer_scoring_enabled:true}).success).toBe(false);
    expect(studyAssignmentSchema.parse({id,expires_at:"time",not_before:"time",repeat:true})).not.toHaveProperty("repeat");
    expect(translate("zh-CN","left")).toBe("更喜欢左侧");
    expect(translate("zh-CN","right")).toBe("更喜欢右侧");
    for(const key of ["Front-facing","Left-facing","Right-facing","Other pose","Diffuse lighting","Side lighting","Low light","Other lighting","DRAFT","OPEN","PAUSED","CLOSED","SEALED","contributor","rater","custodian","I confirm I am an adult (18+).","I read and understood this version and am participating voluntarily.","I authorize the described private research processing, human ratings and research-derived weights, without commercial or public-display permission.","I confirm this is an authorized test-fixture workflow, not real participant collection."]) expect(translate("zh-CN",key)).not.toBe(key);
  });
});
