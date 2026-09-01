package com.macro.mall.portal.domain;

/** Minimal broker command passed to an approved fulfillment adapter. */
public class AiAfterSalesFulfillmentCommand {
    private String eventId;
    private Long applicationId;
    private String commandType;

    public String getEventId() { return eventId; }
    public void setEventId(String eventId) { this.eventId = eventId; }
    public Long getApplicationId() { return applicationId; }
    public void setApplicationId(Long applicationId) { this.applicationId = applicationId; }
    public String getCommandType() { return commandType; }
    public void setCommandType(String commandType) { this.commandType = commandType; }
}
