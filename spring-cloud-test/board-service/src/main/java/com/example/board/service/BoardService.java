package com.example.board.service;

import com.example.board.domain.Board;
import com.example.board.dto.BoardRequest;
import java.time.LocalDateTime;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.stereotype.Service;

/**
 * 외부 DB 없이 메모리(Map)에 게시글을 저장하는 테스트용 서비스.
 * 서버를 재시작하면 데이터가 초기화된다.
 */
@Service
public class BoardService {

    private final Map<Long, Board> store = new ConcurrentHashMap<>();
    private final AtomicLong sequence = new AtomicLong();

    public BoardService() {
        create(new BoardRequest("첫 번째 게시글", "Spring Cloud 테스트 게시판입니다.", "admin"));
        create(new BoardRequest("두 번째 게시글", "API Gateway 를 통해 호출해 보세요.", "user"));
    }

    public List<Board> findAll() {
        return store.values().stream()
                .sorted(Comparator.comparing(Board::getId).reversed())
                .toList();
    }

    public Optional<Board> findById(Long id) {
        return Optional.ofNullable(store.get(id));
    }

    public Board create(BoardRequest request) {
        LocalDateTime now = LocalDateTime.now();
        Board board = Board.builder()
                .id(sequence.incrementAndGet())
                .title(request.getTitle())
                .content(request.getContent())
                .author(request.getAuthor())
                .createdAt(now)
                .updatedAt(now)
                .build();
        store.put(board.getId(), board);
        return board;
    }

    public Optional<Board> update(Long id, BoardRequest request) {
        return findById(id).map(board -> {
            if (request.getTitle() != null) {
                board.setTitle(request.getTitle());
            }
            if (request.getContent() != null) {
                board.setContent(request.getContent());
            }
            board.setUpdatedAt(LocalDateTime.now());
            return board;
        });
    }

    public boolean delete(Long id) {
        return store.remove(id) != null;
    }
}
