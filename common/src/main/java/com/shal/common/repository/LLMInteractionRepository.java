package com.shal.common.repository;

import com.shal.common.entity.LLMInteraction;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.Optional;

/**
 * Repository for stored LLM exchanges. The reviewer "why this verdict" drawer
 * looks a row up by its SHALqc interaction id (the card's llmInteractionId).
 */
@Repository
public interface LLMInteractionRepository extends JpaRepository<LLMInteraction, Long> {

    Optional<LLMInteraction> findByInteractionId(String interactionId);

    List<LLMInteraction> findByQcResultId(Long qcResultId);
}
