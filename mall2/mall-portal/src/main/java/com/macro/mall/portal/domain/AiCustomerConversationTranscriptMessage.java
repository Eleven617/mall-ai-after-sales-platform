package com.macro.mall.portal.domain;

/** Message accepted only from FastAPI after it has produced a public response. */
public class AiCustomerConversationTranscriptMessage {
    private String role;
    private String content;
    private String publicResponseJson;

    public String getRole() { return role; }
    public void setRole(String role) { this.role = role; }
    public String getContent() { return content; }
    public void setContent(String content) { this.content = content; }
    public String getPublicResponseJson() { return publicResponseJson; }
    public void setPublicResponseJson(String publicResponseJson) { this.publicResponseJson = publicResponseJson; }
}
