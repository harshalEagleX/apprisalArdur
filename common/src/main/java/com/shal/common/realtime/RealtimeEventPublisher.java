package com.shal.common.realtime;

public interface RealtimeEventPublisher {

    void publish(String topic, Object payload);
}
