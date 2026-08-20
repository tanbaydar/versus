-- VERSUS schema
-- Run: mysql -u root -p < schema.sql

DROP DATABASE IF EXISTS versus;
CREATE DATABASE versus;
USE versus;

CREATE TABLE Users ( 
    user_id       INT AUTO_INCREMENT PRIMARY KEY,
    username      VARCHAR(50)  NOT NULL UNIQUE,
    email         VARCHAR(255) NOT NULL UNIQUE,
    password      VARCHAR(255) NOT NULL,
    bio           TEXT,
    created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE Brackets (
    bracket_id           INT AUTO_INCREMENT PRIMARY KEY,
    host_id              INT NOT NULL,
    title                VARCHAR(255) NOT NULL,
    description          TEXT,
    entrant_count        INT NOT NULL,
    status               ENUM(
                             'draft',
                             'predictions_open',
                             'round_1','round_2','round_3','round_4','round_5',
                             'completed'
                         ) NOT NULL DEFAULT 'predictions_open',
	prediction_deadline	 DATETIME, 
    created_at           DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_entrant_count CHECK (entrant_count IN (4,8,16,32)),
    CONSTRAINT fk_brackets_host  FOREIGN KEY (host_id) REFERENCES Users(user_id)
);

CREATE TABLE Entrants (
    entrant_id   INT AUTO_INCREMENT PRIMARY KEY,
    bracket_id   INT NOT NULL,
    seed         INT NOT NULL,
    name         VARCHAR(255) NOT NULL,
    image_URL    VARCHAR(255),
    CONSTRAINT fk_entrants_bracket FOREIGN KEY (bracket_id) REFERENCES Brackets(bracket_id),
    CONSTRAINT uq_entrants_seed    UNIQUE (bracket_id, seed)
);

CREATE TABLE Matchups (
    matchup_id          INT AUTO_INCREMENT PRIMARY KEY,
    bracket_id          INT NOT NULL,
    round               INT NOT NULL,
    slot                INT NOT NULL,
    entrant_a_id        INT,
    entrant_b_id        INT,
    winner_entrant_id   INT,
    votes_a             INT NOT NULL DEFAULT 0,
    votes_b             INT NOT NULL DEFAULT 0,
    CONSTRAINT chk_entrant1_entrant2 CHECK (entrant_a_id <> entrant_b_id),
    CONSTRAINT chk_winner_entrants CHECK (winner_entrant_id IN (entrant_a_id, entrant_b_id)),
    CONSTRAINT fk_matchups_bracket FOREIGN KEY (bracket_id)        REFERENCES Brackets(bracket_id),
    CONSTRAINT fk_matchups_a       FOREIGN KEY (entrant_a_id)      REFERENCES Entrants(entrant_id),
    CONSTRAINT fk_matchups_b       FOREIGN KEY (entrant_b_id)      REFERENCES Entrants(entrant_id),
    CONSTRAINT fk_matchups_winner  FOREIGN KEY (winner_entrant_id) REFERENCES Entrants(entrant_id),
    CONSTRAINT uq_matchups_slot    UNIQUE (bracket_id, round, slot)
);

CREATE TABLE Achievements ( 
	code VARCHAR(50) PRIMARY KEY,
    name VARCHAR(255) NOT NULL, 
    description TEXT NOT NULL 
);

INSERT INTO Achievements (code, name, description) VALUES
('bracket_maker', 'Bracket Maker', 'Hosted your first bracket.'),
('locked_in', 'Locked In', 'Submitted your 10th prediction.');

CREATE TABLE Predictions (
prediction_id INT AUTO_INCREMENT PRIMARY KEY,
user_id INT NOT NULL,
matchup_id INT NOT NULL,
entrant_id INT NOT NULL,
is_correct BOOLEAN,
points_earned INT NOT NULL DEFAULT 0,
submitted_at DATETIME NOT NULL, 
CONSTRAINT uq_predictions_matchup   UNIQUE (user_id, matchup_id),
CONSTRAINT fk_predictions_user FOREIGN KEY (user_id) REFERENCES Users(user_id),
CONSTRAINT fk_predictions_matchup FOREIGN KEY (matchup_id) REFERENCES Matchups(matchup_id),
CONSTRAINT fk_predictions_entrant FOREIGN KEY (entrant_id) REFERENCES Entrants(entrant_id)
);

CREATE TABLE Votes (
vote_id INT AUTO_INCREMENT PRIMARY KEY,
user_id INT NOT NULL,
matchup_id INT NOT NULL,
entrant_id INT NOT NULL,
CONSTRAINT fk_votes_user FOREIGN KEY (user_id) REFERENCES Users(user_id),
CONSTRAINT fk_votes_matchup FOREIGN KEY (matchup_id) REFERENCES Matchups(matchup_id),
CONSTRAINT fk_votes_entrant FOREIGN KEY (entrant_id) REFERENCES Entrants(entrant_id),
CONSTRAINT uq_votes_matchup UNIQUE (user_id, matchup_id)
);

CREATE TABLE user_achievements (
user_id INT NOT NULL,
code VARCHAR(50) NOT NULL,
earned_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
PRIMARY KEY (user_id, code),
CONSTRAINT fk_user_achievements_user FOREIGN KEY (user_id) REFERENCES Users(user_id),
CONSTRAINT fk_user_achievements_achievement FOREIGN KEY (code) REFERENCES Achievements(code)
);

CREATE TABLE Follows (
follower_id INT NOT NULL,
followed_id INT NOT NULL,
created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
PRIMARY KEY(follower_id, followed_id),
CONSTRAINT chk_followers CHECK (follower_id <> followed_id),
CONSTRAINT fk_follows_follower FOREIGN KEY (follower_id) REFERENCES Users(user_id),
CONSTRAINT fk_follows_followed FOREIGN KEY (followed_id) REFERENCES Users(user_id)
);

CREATE TABLE Comments (
comment_id INT AUTO_INCREMENT PRIMARY KEY,
user_id INT NOT NULL,
matchup_id INT NOT NULL,
body TEXT NOT NULL,
created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
CONSTRAINT fk_comments_user FOREIGN KEY (user_id) REFERENCES Users(user_id),
CONSTRAINT fk_comments_matchup FOREIGN KEY (matchup_id) REFERENCES Matchups(matchup_id)
);


CREATE INDEX idx_matchups_bracket ON Matchups(bracket_id);
CREATE INDEX idx_predictions_user ON Predictions(user_id);
CREATE INDEX idx_follows_followed ON Follows(followed_id);



DELIMITER $$ 

CREATE TRIGGER predictionsOpen
    BEFORE INSERT 
    ON Predictions FOR EACH ROW
BEGIN
    IF (SELECT B.status
        FROM Matchups M, Brackets B
        WHERE M.matchup_id = NEW.matchup_id
        AND M.bracket_id = B.bracket_id) <> 'predictions_open'
    THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Predictions may only be submitted while the bracket is in the predictions_open state.';
    END IF;
END $$

DELIMITER ;

DELIMITER $$ 

CREATE TRIGGER voteCurrentRound
BEFORE INSERT 
ON Votes FOR EACH ROW
BEGIN
    IF NOT EXISTS 
    (SELECT *
    FROM Matchups M JOIN Brackets B ON M.bracket_id = B.bracket_id
    WHERE M.matchup_id = NEW.matchup_id
        AND (
        (M.round = 1 AND B.status = 'round_1') OR
        (M.round = 2 AND B.status = 'round_2') OR
        (M.round = 3 AND B.status = 'round_3') OR
        (M.round = 4 AND B.status = 'round_4') OR
        (M.round = 5 AND B.status = 'round_5')          
        ))
THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Votes may only be cast on a matchups whose round equals the brackets current round.';
    END IF;
END $$

DELIMITER ;


DELIMITER $$ 

CREATE TRIGGER awardBracketMaker
AFTER INSERT  ON Brackets FOR EACH ROW
BEGIN
    IF (SELECT COUNT(*)
        FROM Brackets B
        WHERE B.host_id = NEW.host_id) = 1
    THEN 
        INSERT INTO user_achievements (user_id, code)
        VALUES (NEW.host_id, 'bracket_maker');
    END IF;

END$$

DELIMITER ;


DELIMITER $$ 

CREATE TRIGGER awardLockedIn
AFTER INSERT ON Predictions FOR EACH ROW
BEGIN
    IF (SELECT COUNT(*)
        FROM Predictions P
        WHERE P.user_id = NEW.user_id) = 10
    THEN 
        INSERT INTO user_achievements (user_id, code)
        VALUES (NEW.user_id, 'locked_in');
    END IF;

END$$

DELIMITER ;


DELIMITER $$

CREATE PROCEDURE close_round(IN p_bracket_id INT, IN p_round INT)
BEGIN
    DECLARE v_slot   INT;
    DECLARE v_winner INT;
    DECLARE done     INT DEFAULT FALSE;
    DECLARE cur CURSOR FOR
        SELECT slot, winner_entrant_id
        FROM Matchups
        WHERE bracket_id = p_bracket_id AND round = p_round;
    DECLARE CONTINUE HANDLER FOR NOT FOUND SET done = TRUE;

    -- Reject invalid or repeated transitions before changing tournament data.
    IF NOT EXISTS (
        SELECT 1
        FROM Brackets
        WHERE bracket_id = p_bracket_id
          AND status = CONCAT('round_', p_round)
    ) THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Bracket is not in the requested active round.';
    END IF;

    -- Every active matchup must be fully populated before it can be resolved.
    IF EXISTS (
        SELECT 1
        FROM Matchups
        WHERE bracket_id = p_bracket_id
          AND round = p_round
          AND (entrant_a_id IS NULL OR entrant_b_id IS NULL)
    ) THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Active round contains an incomplete matchup.';
    END IF;

    -- 1. winners from vote totals; ties go to the better-seeded entrant
    UPDATE Matchups m
    JOIN Entrants ea ON ea.entrant_id = m.entrant_a_id
    JOIN Entrants eb ON eb.entrant_id = m.entrant_b_id
    SET m.winner_entrant_id = CASE
        WHEN m.votes_a > m.votes_b THEN m.entrant_a_id
        WHEN m.votes_b > m.votes_a THEN m.entrant_b_id
        WHEN ea.seed <= eb.seed THEN m.entrant_a_id
        ELSE m.entrant_b_id
    END
    WHERE m.bracket_id = p_bracket_id AND m.round = p_round;

    -- 2. score this round's predictions; one point per correct prediction
    UPDATE Predictions
    SET is_correct =
            CASE WHEN entrant_id =
                (SELECT M.winner_entrant_id FROM Matchups M
                 WHERE M.matchup_id = Predictions.matchup_id)
            THEN TRUE ELSE FALSE END,
        points_earned =
            CASE WHEN entrant_id =
                (SELECT M.winner_entrant_id FROM Matchups M
                 WHERE M.matchup_id = Predictions.matchup_id)
            THEN 1 ELSE 0 END
    WHERE matchup_id IN
        (SELECT matchup_id FROM Matchups
         WHERE bracket_id = p_bracket_id AND round = p_round);

    -- 3. promote winners into the next round
    OPEN cur;
    promote_loop: LOOP
        FETCH cur INTO v_slot, v_winner;
        IF done THEN LEAVE promote_loop; END IF;
        IF MOD(v_slot, 2) = 1 THEN
            UPDATE Matchups SET entrant_a_id = v_winner
            WHERE bracket_id = p_bracket_id AND round = p_round + 1
              AND slot = (v_slot + 1) DIV 2;
        ELSE
            UPDATE Matchups SET entrant_b_id = v_winner
            WHERE bracket_id = p_bracket_id AND round = p_round + 1
              AND slot = v_slot DIV 2;
        END IF;
    END LOOP;
    CLOSE cur;

    -- 4. advance status, or complete the bracket after the final round
    IF p_round = (SELECT MAX(round) FROM Matchups WHERE bracket_id = p_bracket_id) THEN
        UPDATE Brackets SET status = 'completed' WHERE bracket_id = p_bracket_id;
    ELSEIF p_round = 1 THEN
        UPDATE Brackets SET status = 'round_2' WHERE bracket_id = p_bracket_id;
    ELSEIF p_round = 2 THEN
        UPDATE Brackets SET status = 'round_3' WHERE bracket_id = p_bracket_id;
    ELSEIF p_round = 3 THEN
        UPDATE Brackets SET status = 'round_4' WHERE bracket_id = p_bracket_id;
    ELSEIF p_round = 4 THEN
        UPDATE Brackets SET status = 'round_5' WHERE bracket_id = p_bracket_id;
    END IF;
END$$

DELIMITER ;
