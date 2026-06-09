#pragma once
// ============================================================
//  GroundEye — SQLite Event Logger
// ============================================================

#include "orchestrator.hpp"
#include <sqlite3.h>
#include <iostream>
#include <stdexcept>
#include <filesystem>

namespace groundeye {

    class EventLogger {
    public:
        explicit EventLogger(const std::string& db_path) {
            // Klasör yoksa oluştur
            std::filesystem::path p(db_path);
            if (p.has_parent_path())
                std::filesystem::create_directories(p.parent_path());

            if (sqlite3_open(db_path.c_str(), &db_) != SQLITE_OK) {
                throw std::runtime_error(
                    std::string("SQLite açılamadı: ") + sqlite3_errmsg(db_));
            }
            createTables();
            std::cout << "[SQLite] Veritabanı: " << db_path << "\n";
        }

        ~EventLogger() {
            if (db_) sqlite3_close(db_);
        }

        // Fused event kaydet
        void log(const FusedEvent& fe) {
            const char* sql = R"(
            INSERT INTO fused_events
                (timestamp_ms, best_method, best_x, best_y,
                 amp_x, amp_y, amp_confidence,
                 tdoa_x, tdoa_y, tdoa_confidence,
                 est_dist_m, nearest_node, node_count, tdoa_used)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?);
        )";

        sqlite3_stmt* stmt = nullptr;
        sqlite3_prepare_v2(db_, sql, -1, &stmt, nullptr);
        sqlite3_bind_int64(stmt,  1, static_cast<int64_t>(fe.timestamp_ms));
        sqlite3_bind_text(stmt,   2, fe.best_method.c_str(), -1, SQLITE_STATIC);
        sqlite3_bind_double(stmt, 3, fe.best.x);
        sqlite3_bind_double(stmt, 4, fe.best.y);
        sqlite3_bind_double(stmt, 5, fe.amplitude.x);
        sqlite3_bind_double(stmt, 6, fe.amplitude.y);
        sqlite3_bind_double(stmt, 7, fe.amplitude.confidence);
        sqlite3_bind_double(stmt, 8, fe.tdoa.valid ? fe.tdoa.x : -1.0);
        sqlite3_bind_double(stmt, 9, fe.tdoa.valid ? fe.tdoa.y : -1.0);
        sqlite3_bind_double(stmt,10, fe.tdoa.valid ? fe.tdoa.confidence : 0.0);
        sqlite3_bind_double(stmt,11, fe.est_dist_m);
        sqlite3_bind_text(stmt,  12, fe.nearest_node.c_str(), -1, SQLITE_STATIC);
        sqlite3_bind_int(stmt,   13, fe.node_count);
        sqlite3_bind_int(stmt,   14, fe.tdoa_used ? 1 : 0);
        sqlite3_step(stmt);

        int64_t fused_id = sqlite3_last_insert_rowid(db_);
        sqlite3_finalize(stmt);

        // Ham node eventlarını da kaydet
        for (const auto& e : fe.events) {
            logNodeEvent(fused_id, e);
        }
        }

    private:
        sqlite3* db_ = nullptr;

        void createTables() {
            const char* sql = R"(
            CREATE TABLE IF NOT EXISTS fused_events (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp_ms   INTEGER NOT NULL,
                best_method    TEXT,
                best_x         REAL,
                best_y         REAL,
                amp_x          REAL,
                amp_y          REAL,
                amp_confidence REAL,
                tdoa_x         REAL,
                tdoa_y         REAL,
                tdoa_confidence REAL,
                est_dist_m     REAL,
                nearest_node   TEXT,
                node_count     INTEGER,
                tdoa_used      INTEGER
            );

            CREATE TABLE IF NOT EXISTS node_events (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                fused_id     INTEGER REFERENCES fused_events(id),
                node_id      TEXT    NOT NULL,
                onset_ms     INTEGER,
                peak_ms      INTEGER,
                rms_energy   REAL,
                peak_amplitude REAL,
                duration_ms  REAL
            );

            CREATE INDEX IF NOT EXISTS idx_fused_ts
            ON fused_events(timestamp_ms);
            )";

        char* err = nullptr;
        if (sqlite3_exec(db_, sql, nullptr, nullptr, &err) != SQLITE_OK) {
            std::string msg(err);
            sqlite3_free(err);
            throw std::runtime_error("Tablo oluşturulamadı: " + msg);
        }
        }

        void logNodeEvent(int64_t fused_id, const NodeEvent& e) {
            const char* sql = R"(
            INSERT INTO node_events
                (fused_id, node_id, onset_ms, peak_ms,
                 rms_energy, peak_amplitude, duration_ms)
            VALUES (?, ?, ?, ?, ?, ?, ?);
        )";
        sqlite3_stmt* stmt = nullptr;
        sqlite3_prepare_v2(db_, sql, -1, &stmt, nullptr);
        sqlite3_bind_int64(stmt, 1, fused_id);
        sqlite3_bind_text(stmt, 2, e.node_id.c_str(), -1, SQLITE_STATIC);
        sqlite3_bind_int64(stmt, 3, static_cast<int64_t>(e.onset_ms));
        sqlite3_bind_int64(stmt, 4, static_cast<int64_t>(e.peak_ms));
        sqlite3_bind_double(stmt, 5, e.rms_energy);
        sqlite3_bind_double(stmt, 6, e.peak_amplitude);
        sqlite3_bind_double(stmt, 7, e.duration_ms);
        sqlite3_step(stmt);
        sqlite3_finalize(stmt);
        }
    };

} // namespace groundeye
