from django.db import migrations


def apply_triggers(apps, schema_editor):
    connection = schema_editor.connection
    if connection.vendor == 'postgresql':
        with connection.cursor() as cursor:
            cursor.execute("""
            CREATE OR REPLACE FUNCTION check_journal_entry_immutability()
            RETURNS TRIGGER AS $$
            BEGIN
                IF (OLD.status = 'posted') THEN
                    IF (TG_OP = 'DELETE') THEN
                        RAISE EXCEPTION 'IMMUTABLE_LEDGER_ERROR: Posted journal entry ID % cannot be deleted.', OLD.id;
                    ELSIF (TG_OP = 'UPDATE') THEN
                        IF (
                            OLD.id IS DISTINCT FROM NEW.id OR
                            OLD.number IS DISTINCT FROM NEW.number OR
                            OLD.date IS DISTINCT FROM NEW.date OR
                            OLD.period_id IS DISTINCT FROM NEW.period_id OR
                            OLD.posted_at IS DISTINCT FROM NEW.posted_at OR
                            OLD.posted_by_id IS DISTINCT FROM NEW.posted_by_id OR
                            OLD.posting_source IS DISTINCT FROM NEW.posting_source OR
                            OLD.posting_reference IS DISTINCT FROM NEW.posting_reference OR
                            OLD.status IS DISTINCT FROM NEW.status
                        ) THEN
                            RAISE EXCEPTION 'IMMUTABLE_LEDGER_ERROR: Posted journal entry ID % header fields are strictly immutable (only reversed_by_entry_id update permitted).', OLD.id;
                        END IF;
                    END IF;
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;

            DROP TRIGGER IF EXISTS trg_check_journal_entry_immutability ON financial_journalentry;
            CREATE TRIGGER trg_check_journal_entry_immutability
            BEFORE UPDATE OR DELETE ON financial_journalentry
            FOR EACH ROW EXECUTE FUNCTION check_journal_entry_immutability();

            CREATE OR REPLACE FUNCTION check_journal_line_immutability()
            RETURNS TRIGGER AS $$
            DECLARE
                target_entry_id BIGINT;
                entry_status VARCHAR(20);
            BEGIN
                IF (TG_OP = 'INSERT') THEN
                    target_entry_id := NEW.journal_entry_id;
                ELSE
                    target_entry_id := OLD.journal_entry_id;
                END IF;

                SELECT status INTO entry_status FROM financial_journalentry WHERE id = target_entry_id;

                IF (entry_status = 'posted') THEN
                    RAISE EXCEPTION 'IMMUTABLE_LEDGER_ERROR: Line operation % on posted journal entry ID % is strictly forbidden.', TG_OP, target_entry_id;
                END IF;

                IF (TG_OP = 'DELETE') THEN
                    RETURN OLD;
                ELSE
                    RETURN NEW;
                END IF;
            END;
            $$ LANGUAGE plpgsql;

            DROP TRIGGER IF EXISTS trg_check_journal_line_immutability ON financial_journalentryline;
            CREATE TRIGGER trg_check_journal_line_immutability
            BEFORE INSERT OR UPDATE OR DELETE ON financial_journalentryline
            FOR EACH ROW EXECUTE FUNCTION check_journal_line_immutability();
            """)


def remove_triggers(apps, schema_editor):
    connection = schema_editor.connection
    if connection.vendor == 'postgresql':
        with connection.cursor() as cursor:
            cursor.execute("""
            DROP TRIGGER IF EXISTS trg_check_journal_entry_immutability ON financial_journalentry;
            DROP FUNCTION IF EXISTS check_journal_entry_immutability();
            DROP TRIGGER IF EXISTS trg_check_journal_line_immutability ON financial_journalentryline;
            DROP FUNCTION IF EXISTS check_journal_line_immutability();
            """)


class Migration(migrations.Migration):

    dependencies = [
        ('financial', '0002_initial'),
    ]

    operations = [
        migrations.RunPython(apply_triggers, remove_triggers)
    ]
