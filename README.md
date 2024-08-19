## Create mysql database with name "users_data"

### columns:
- date
- time
- test_status
- user_id
- run_date

### test_status info:

- None - without datetime
- 1 - waiting start of test
- 2 - test started
- 3 - test ending notification
- 4 - result sent
- 5 - test failed
- 6 - test completed

```
create table users_data
(
    date        varchar(255) null,
    time        varchar(255) null,
    test_status int          null,
    user_id     bigint       null,
    run_date    varchar(255) null,
    username    varchar(255) null,
    on_task     varchar(255) null
);

```